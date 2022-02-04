import random
import pathlib 
import os 
import argparse
from itertools import product 

import numpy as np 
from scipy.stats import loguniform

def run_search(
    num: int, 
    class_label: str
) -> None:
    """
    
    """
    here = pathlib.Path(__file__).parent.absolute()
    yaml_path = os.path.join(here, '..', '..', 'yaml', 'model.yaml')

    param_dict = {
        'class_label': [class_label],
        'epochs': [100000],
        'lr': np.linspace(0.001, 0.1, 10), #(start, stop, num),
        'batch_size': [2, 4, 16, 32],
        'momentum': np.linspace(0.001, 0.9, 10),
        'weight_decay': loguniform.rvs(0.001, 0.1, size=10),
        'width': [1024, 2048, 4096],
        'layers': np.arange(10, 25, 5),
    }

    # Generate cartesian product of dictionary 
    params = list(product(*param_dict.values()))
    param_names = list(param_dict.keys())
    
    for i, params in enumerate(random.sample(params, num)):
        for n, p in zip(param_names, params):
            os.environ[n.upper()] = str(p)

        # These two are to put in job name
        os.environ['NAME'] = class_label.lower()
        os.environ['I'] = str(i) 
        os.system(f'envsubst < {yaml_path} | kubectl create -f -')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(usage='Hyperparameter tune with random search.')

    parser.add_argument(
        '--N',
        help='Number of experiments to run',
        required=False,
        type=int,
        default=100,
    )
    
    parser.add_argument(
        '--class-label',
        help='Class to train classifer on',
        required=False,
        default='Subtype',
        type=str,
    )

    args = parser.parse_args()

    run_search(args.N, args.class_label)