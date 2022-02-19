import pathlib 
import os 
import sys
import argparse
import urllib 

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import helper 

here = pathlib.Path(__file__).parent.absolute()
data_path = os.path.join(here, '..', '..', 'data')

def _download_from_key(key, localpath):
    """
    Helper function that downloads all files recursively from the given key (folder) from the braingeneersdev S3 bucket
    
    Parameters:
    key: S3 folder (key) to start downloading recursively from
    localpath: Optional argument, downloads to a subfolder under the data/processed/ folder # TODO add folder generation
    """

    print(f'Key is {key}')
    reduced_files = helper.list_objects(key)

    if not os.path.exists(localpath):
        print(f'Download path {localpath} doesn\'t exist, creating...')
        os.makedirs(localpath, exist_ok=True)

    for f in reduced_files:
        if not os.path.isfile(os.path.join(data_path, 'processed', f.split('/')[-1])):
            print(f'Downloading {f} from S3')
            helper.download(
                f,
                os.path.join(localpath, f.split('/')[-1]) # Just the file name in the list of objects
            )

def download_clean_from_s3(
    file: str=None,
    local_path: str=None,
) -> None:
    """Downloads the cleaned data from s3 to be used in model training."""

    os.makedirs(os.path.join(data_path, 'processed'), exist_ok=True)
    if not file: # No single file passed, so download recursively
        print('Downloading all clean data...')
        key = os.path.join('jlehrer', 'expression_data', 'processed')
        local_path = os.path.join(data_path, 'processed')

        _download_from_key(key, local_path) 
    else:
        print(f'Downloading {file} from clean data')
        local_path = (os.path.join(data_path, 'processed', file) if not local_path else local_path)
        helper.download(
            os.path.join('jlehrer', 'expression_data', 'processed', file),
            local_path
        )

def download_interim_from_s3(
    file: str=None,
    local_path: str=None,
) -> None:
    """Downloads the interim data from S3. Interim data is in the correct structural format but has not been cleaned."""

    os.makedirs(os.path.join(data_path, 'interim'), exist_ok=True)

    if not file:
        print('Downloading all interim data')
        key = os.path.join('jlehrer', 'expression_data', 'interim')
        local_path = os.path.join(data_path, 'interim')
        _download_from_key(key, local_path)
    else:
        print(f'Downloading {file} from interim data')
        local_path = (os.path.join(data_path, 'interim', file) if not local_path else local_path)
        helper.download(
            os.path.join('jlehrer', 'expression_data', 'interim', file), 
            local_path
        )
        
def download_raw_from_s3(
    file: str=None,
    local_path: str=None,
) -> None:
    """Downloads the raw expression matrices from s3"""

    os.makedirs(os.path.join(data_path, 'raw'), exist_ok=True)
    if not file: 
        print('Downloading all raw data')
        key = os.path.join('jlehrer', 'expression_data', 'raw')
        local_path = os.path.join(data_path, 'raw')
        _download_from_key(key, local_path)
    else:
        print(f'Downloading {file} from raw data')
        local_path = (os.path.join(data_path, 'raw', file) if not local_path else local_path)
        helper.download(
            os.path.join('jlehrer', 'expression_data', 'raw', file), 
            local_path
        )

def download_raw_expression_matrices(upload: bool) -> None:
    """Downloads all raw datasets and label sets from cells.ucsc.edu, and then unzips them locally
    
    Parameters:
    upload: Whether or not to also upload data to S3 bucket 
    """

    # {local file name: [dataset url, labelset url]}
    datasets = helper.DATA_FILES_AND_URLS_DICT

    for file, links in datasets.items():
        datafile_path = os.path.join(data_path, 'raw', file)

        labelfile = f'{file[:-4]}_labels.tsv'
        labelfile_path = os.path.join(data_path, 'raw', labelfile)

        datalink, labellink = links 

        # First, make the required folders if they do not exist 
        for dir in 'raw', 'interim', 'processed':
            os.makedirs(os.path.join(data_path, dir), exist_ok=True)

        # Download and unzip data file if it doesn't exist 
        if not os.path.isfile(os.path.join(data_path, 'raw', file)):
            print(f'Downloading zipped data for {file}')
            urllib.request.urlretrieve(
                datalink,
                f'{datafile_path}.gz',
            )

            print(f'Unzipping {file}')
            os.system(
                f'zcat < {datafile_path}.gz > {datafile_path}'
            )

            print(f'Deleting compressed data')
            os.system(
                f'rm -rf {datafile_path}.gz'
            )

        # Download label file if it doesn't exist 
        if not os.path.isfile(os.path.join(data_path, 'raw', labelfile_path)):
            print(f'Downloading label for {file}')
            urllib.request.urlretrieve(
                labellink,
                labelfile_path,
            )

        # If upload boolean is passed, also upload these files to the braingeneersdev s3 bucket
        if upload:
            print(f'Uploading {file} and {labelfile} to braingeneersdev S3 bucket')
            helper.upload(
                datafile_path,
                os.path.join('jlehrer', 'expression_data', 'raw', file)
            )

            helper.upload(
                labelfile_path,
                os.path.join('jlehrer', 'expression_data', 'raw', f'{file[:-4]}_labels.tsv')
            )

    print('Done.')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--type',
        type=str,
        required=False,
        default='clean',
        help="Type of data to download"
    )

    parser.add_argument(
        '--s3-upload',
        required=False,
        action='store_true',
        help='If passed, also upload data to braingeneersdev/jlehrer/expression_data/raw, if the method accepts this option'
    )

    parser.add_argument(
        '--key',
        required=False,
        default=None,
        type=str,
        help='If not None, only download the specific key passed in this argument from the braingeneersdev s3 bucket'
    )   

    parser.add_argument(
        '--local-name',
        required=False,
        default=None,
        help='If not None, download the key specified from the --file flag into this local filename'
    )

    args = parser.parse_args()

    type = args.type
    upload = args.s3_upload
    key = args.key 
    local = args.local_name 

    if local is not None and not key:
        parser.error('Error: If --local-name is passed in specified download, s3 key must be passed as well via --key')

    if type == 'external':
        download_raw_expression_matrices(upload=upload)
    if type == 'interim':
        download_interim_from_s3(key, local)
    elif type == 'raw':
        download_raw_from_s3(key, local)
    elif type == 'processed' or type == 'clean':
        download_clean_from_s3(key, local)
    else:
        raise ValueError('Unknown type specified for data downloading.')