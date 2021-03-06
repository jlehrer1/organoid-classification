from typing import *

import torch 
import numpy as np 
import shutil 
import json 
import zipfile 
import io 
import pytorch_lightning as pl 
from scipy.sparse import csc_matrix 
from pathlib import Path 
from pytorch_tabnet.utils import (
    create_explain_matrix,
    ComplexEncoder,
)
import torch.nn.functional as F
from torchmetrics.functional import accuracy, precision, recall 
from pytorch_tabnet.tab_network import TabNet
import copy
import warnings
from functools import cached_property

class TabNetLightning(pl.LightningModule):
    def __init__(
        self,
        input_dim,
        output_dim,
        n_d=8,
        n_a=8,
        n_steps=3,
        gamma=1.3,
        cat_idxs=[],
        cat_dims=[],
        cat_emb_dim=1,
        n_independent=2,
        n_shared=2,
        epsilon=1e-15,
        virtual_batch_size=128,
        momentum=0.02,
        mask_type="sparsemax",
        lambda_sparse = 1e-3,
        optim_params: Dict[str, float]={
            'optimizer': torch.optim.Adam,
            'lr': 0.001,
            'weight_decay': 0.01,
        },
        metrics: Dict[str, Callable]={
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
        },
        scheduler_params: Dict[str, float]=None,
        weighted_metrics=False,
        weights=None,
        loss=None, # will default to cross_entropy
        pretrained=None,
    ) -> None:
        super().__init__()

        # Stuff needed for training
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.lambda_sparse = lambda_sparse

        self.optim_params = optim_params
        self.scheduler_params = scheduler_params
        self.metrics = metrics
        self.weighted_metrics = weighted_metrics
        self.weights = weights 
        self.loss = loss 

        if pretrained is not None:
            self._from_pretrained(**pretrained.get_params())
        # self.device = ('cuda:0' if torch.cuda.is_available() else 'cpu!')

        print(f'Initializing network')
        self.network = TabNet(
            input_dim=input_dim, 
            output_dim=output_dim, 
            n_d=n_d,
            n_a=n_a,
            n_steps=n_steps,
            gamma=gamma,
            cat_idxs=cat_idxs,
            cat_dims=cat_dims,
            cat_emb_dim=cat_emb_dim,
            n_independent=n_independent,
            n_shared=n_shared,
            epsilon=epsilon,
            virtual_batch_size=virtual_batch_size,
            momentum=momentum,
            mask_type=mask_type,
        )

        print(f'Initializing explain matrix')
        self.reducing_matrix = create_explain_matrix(
            self.network.input_dim,
            self.network.cat_emb_dim,
            self.network.cat_idxs,
            self.network.post_embed_dim,
        )

    def forward(self, x):
        return self.network(x)

    def _compute_loss(self, y, y_hat):
        # If user doesn't specify, just set to cross_entropy
        if self.loss is None:
            self.loss = F.cross_entropy 

        return self.loss(y, y_hat, weight=self.weights)

    def _step(self, batch):
        x, y = batch
        y_hat, M_loss = self.network(x)

        loss = self._compute_loss(y_hat, y)

        # Add the overall sparsity loss
        loss = loss - self.lambda_sparse * M_loss
        return y, y_hat, loss

    def training_step(self, batch, batch_idx):
        y, y_hat, loss = self._step(batch)

        self.log("train_loss", loss, logger=True, on_epoch=True, on_step=True)
        self._compute_metrics(y_hat, y, 'train')

        return loss

    def validation_step(self, batch, batch_idx):
        y, y_hat, loss = self._step(batch)

        self.log("val_loss", loss, logger=True, on_epoch=True, on_step=True)
        self._compute_metrics(y_hat, y, 'val')

    def test_step(self, batch, batch_idx):
        y, y_hat, loss = self._step(batch)

        self.log("test_loss", loss, logger=True, on_epoch=True, on_step=True)
        self._compute_metrics(y_hat, y, 'test')

    def configure_optimizers(self):
        if 'optimizer' in self.optim_params:
            optimizer = self.optim_params.pop('optimizer')
            optimizer = optimizer(self.parameters(), **self.optim_params)
        else:
            optimizer = torch.optim.Adam(self.parameters(), lr=0.2, weight_decay=1e-5)

        if self.scheduler_params is not None:
            scheduler = self.scheduler_params.pop('scheduler')
            scheduler = scheduler(optimizer, **self.scheduler_params)

        if self.scheduler_params is None:
            return optimizer
        
        return {
            'optimizer': optimizer,
            'lr_scheduler': scheduler,
            'monitor': 'train_loss',
        }
    
    def _compute_metrics(self, 
        y_hat: torch.Tensor, 
        y: torch.Tensor, 
        tag: str,
        on_epoch=True, 
        on_step=False,
    ):
        """
        Compute metrics for the given batch

        :param y_hat: logits of model
        :type y_hat: torch.Tensor
        :param y: tensor of labels
        :type y: torch.Tensor
        :param tag: log name, to specify train/val/test batch calculation
        :type tag: str
        :param on_epoch: log on epoch, defaults to True
        :type on_epoch: bool, optional
        :param on_step: log on step, defaults to True
        :type on_step: bool, optional
        """
        for name, metric in self.metrics.items():
            if self.weighted_metrics: # We dont consider class support in calculation
                val = metric(y_hat, y, average='weighted', num_classes=self.output_dim)
                self.log(
                    f"weighted_{tag}_{name}", 
                    val, 
                    on_epoch=on_epoch, 
                    on_step=on_step,
                    logger=True,
                )
            else:
                val = metric(y_hat, y, num_classes=self.output_dim)
                self.log(
                    f"{tag}_{name}", 
                    val, 
                    on_epoch=on_epoch, 
                    on_step=on_step,
                    logger=True,
                )

    def explain(self, loader, normalize=False):
        self.network.eval()
        res_explain = []

        for batch_nb, data in enumerate(loader):
            if isinstance(data, tuple): # if we are running this on already labeled pairs and not just for inference
                data, _ = data 
                
            M_explain, masks = self.network.forward_masks(data)
            for key, value in masks.items():
                masks[key] = csc_matrix.dot(
                    value.cpu().detach().numpy(), self.reducing_matrix
                )

            original_feat_explain = csc_matrix.dot(M_explain.cpu().detach().numpy(),
                                                   self.reducing_matrix)
            res_explain.append(original_feat_explain)

            if batch_nb == 0:
                res_masks = masks
            else:
                for key, value in masks.items():
                    res_masks[key] = np.vstack([res_masks[key], value])

        res_explain = np.vstack(res_explain)

        if normalize:
            res_explain /= np.sum(res_explain, axis=1)[:, None]

        return res_explain, res_masks

    def _compute_feature_importances(self, dataloader):
        M_explain, _ = self.explain(dataloader, normalize=False)
        sum_explain = M_explain.sum(axis=0)
        feature_importances_ = sum_explain / np.sum(sum_explain)
        return feature_importances_

    def feature_importances(self, dataloader):
        return self._compute_feature_importances(dataloader)

    def save_model(self, path):
        saved_params = {}
        init_params = {}
        for key, val in self.get_params().items():
            if isinstance(val, type):
                # Don't save torch specific params
                continue
            else:
                init_params[key] = val
        saved_params["init_params"] = init_params

        class_attrs = {
            "preds_mapper": self.preds_mapper
        }
        saved_params["class_attrs"] = class_attrs

        # Create folder
        Path(path).mkdir(parents=True, exist_ok=True)

        # Save models params
        with open(Path(path).joinpath("model_params.json"), "w", encoding="utf8") as f:
            json.dump(saved_params, f, cls=ComplexEncoder)

        # Save state_dict
        torch.save(self.network.state_dict(), Path(path).joinpath("network.pt"))
        shutil.make_archive(path, "zip", path)
        shutil.rmtree(path)
        print(f"Successfully saved model at {path}.zip")
        return f"{path}.zip"

    def load_model(self, filepath):
        try:
            with zipfile.ZipFile(filepath) as z:
                with z.open("model_params.json") as f:
                    loaded_params = json.load(f)
                    loaded_params["init_params"]["device_name"] = self.device_name
                with z.open("network.pt") as f:
                    try:
                        saved_state_dict = torch.load(f, map_location=self.device)
                    except io.UnsupportedOperation:
                        # In Python <3.7, the returned file object is not seekable (which at least
                        # some versions of PyTorch require) - so we'll try buffering it in to a
                        # BytesIO instead:
                        saved_state_dict = torch.load(
                            io.BytesIO(f.read()),
                            map_location=self.device,
                        )
        except KeyError:
            raise KeyError("Your zip file is missing at least one component")

        self.__init__(**loaded_params["init_params"])

        self._set_network()
        self.network.load_state_dict(saved_state_dict)
        self.network.eval()
        self.load_class_attrs(loaded_params["class_attrs"])

    def load_weights_from_unsupervised(self, unsupervised_model):
        update_state_dict = copy.deepcopy(self.network.state_dict())
        for param, weights in unsupervised_model.network.state_dict().items():
            if param.startswith("encoder"):
                # Convert encoder's layers name to match
                new_param = "tabnet." + param
            else:
                new_param = param
            if self.network.state_dict().get(new_param) is not None:
                # update only common layers
                update_state_dict[new_param] = weights

    def _from_pretrained(self, **kwargs):
        update_list = [
            "cat_dims",
            "cat_emb_dim",
            "cat_idxs",
            "input_dim",
            "mask_type",
            "n_a",
            "n_d",
            "n_independent",
            "n_shared",
            "n_steps",
        ]
        for var_name, value in kwargs.items():
            if var_name in update_list:
                try:
                    exec(f"global previous_val; previous_val = self.{var_name}")
                    if previous_val != value:  # noqa
                        wrn_msg = f"Pretraining: {var_name} changed from {previous_val} to {value}"  # noqa
                        warnings.warn(wrn_msg)
                        exec(f"self.{var_name} = value")
                except AttributeError:
                    exec(f"self.{var_name} = value")
