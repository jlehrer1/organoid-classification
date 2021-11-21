import dask.dataframe as da
from dask.diagnostics import ProgressBar
import pathlib 
import os 
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from helper import download, upload

pbar = ProgressBar()
pbar.register() # global registration

here = pathlib.Path(__file__).parent.absolute()

if not os.path.isfile(os.path.join(here, '..', '..', 'data', 'interim', 'organoid_T.csv')):
    print('Downloading raw organoid data from S3')
    download(
        os.path.join('transposed_data', 'organoid_T.csv'), 
        os.path.join(here, '..', '..', 'data', 'interim', 'organoid_T.csv')
    )

if not os.path.isfile(os.path.join(here, '..', '..', 'data', 'interim', 'primary_T.csv')):
    print('Downloading raw primary data from S3')
    download(
        os.path.join('transposed_data', 'primary_T.csv'), 
        os.path.join(here, '..', '..', 'data', 'interim', 'primary_T.csv')
    )

print('Reading in raw organoid data with Dask')
organoid = (da.read_csv(
    os.path.join(here, '..', '..', 'data', 'interim', 'organoid_T.csv'), 
    assume_missing=True)
)

print('Reading in raw primary data with Dask')
primary = (da.read_csv(
    os.path.join(here, '..', '..', 'data', 'interim', 'primary_T.csv'), 
    assume_missing=True)
)

# Fix gene expression names in organoid data
print('Fixing organoid column names')
organoid_cols = [x.split('|')[0] for x in organoid.columns]
organoid.columns = organoid_cols

print('Renaming index')
organoid.index = organoid.index.rename('cell')
primary.index = primary.index.rename('cell')

# Consider only the genes between the two
print('Calculating gene intersection')
subgenes = list(set(organoid.columns).intersection(primary.columns))

print(f'Number of intersecting genes is {len(subgenes)}')
print(f'Type of organoid and primary is {type(organoid)}, {type(primary)}')

# Just keep those genes
organoid = organoid.loc[:, subgenes]
primary = primary.loc[:, subgenes]

# Fill NaN's with zeros
print('Filling NaN\'s with zeros')
organoid = organoid.fillna(0)
primary = primary.fillna(0)

print('Doing all computations')
organoid = organoid.persist()
primary = primary.persist()

# Write out files 
print('Writing out clean organoid data to csv')
organoid.to_csv(os.path.join(here, '..', '..', 'data', 'processed', 'organoid.csv'), single_file=True, index=False)

print('Writing out clean primary data to csv')
primary.to_csv(os.path.join(here, '..', '..', 'data', 'processed', 'primary.csv'), single_file=True, index=False)

print('Uploading files to S3')
upload(os.path.join(here, '..', '..', 'data', 'processed', 'primary.csv'), 'primary.csv')
upload(os.path.join(here, '..', '..', 'data', 'processed', 'organoid.csv'), 'organoid.csv')