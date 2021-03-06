# list_tables imports:
import os
import json
from google.cloud import bigquery
# get_scheduled_queries imports:
from subprocess import check_output, call
import json
import requests
from glob import glob


def del_folder_files(folder, ext=''):
    """
    Given a path to a directory 'folder', delete all files with extension 'ext'.
    """
    file_list = glob(folder + '*' + ext)
    for f in file_list:
        call(['rm', '-f', f])


def list_tables(config):
    """
    Input:
    config - a string for a filename of a json file or dict with
             the required parameters.

    This function lists the tables (on screen and on output) in BigQuery 
    and download queries from views, according to request in the config.

    Return: a list of dicts with table's name and type (external, view or table).
    """

    # Load config from file:
    if type(config) == str:
        with open(config, 'r') as f:
            config = json.load(f)
    if config['table_list_file'] != None:
        save_list = True
        list_file = config['table_list_file']
    else:
        save_list = False
    
    # Set path to BigQuery credentials:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['credentials']

    client = bigquery.Client()

    # Get list of datasets:
    datasets = list(client.list_datasets())

    # Prepare table list file:
    if save_list:
        tf = open(list_file, 'w')

    # Delete previously saved views:
    if config['get_views']:
        #print('Deleting old views...')
        del_folder_files(config['views_path'], '.sql')

    table_list = []
    for dataset in datasets:
        # Print dataset name:
        if config['printout']:
            print('{:40}   {}'.format(dataset.dataset_id, '----------'))
        if save_list:
            tf.write('{:40}   {}\n'.format(dataset.dataset_id, '----------'))
        
        # Get list of tables in the dataset:
        tables = list(client.list_tables(dataset.dataset_id))
        for table in tables:

            # Print table name and type:
            if config['printout']:
                print('  {:40} ({})'.format(table.table_id, table.table_type))
            if save_list:
                tf.write('  {:40} ({})\n'.format(table.table_id, table.table_type))
                
            # Include table (name and type) in list:
            table_list.append({'name': dataset.dataset_id + '.' + table.table_id, 'type': table.table_type})

            if table.table_type == 'VIEW' and config['get_views']:
                # If its a view, save its query to file:
                full_name = table.full_table_id.replace(':','.')
                filename  = table.full_table_id.split(':')[-1]
                objTable  = client.get_table(full_name)
                query     = objTable.view_query
                with open(config['views_path'] + filename + '.sql','w') as f:
                    f.write(query)

        if config['printout']:
            print('')
        if save_list:
            tf.write('\n')

    if save_list:
        tf.close()
    # Return list of dicts with table names and types: 
    return table_list


def get_scheduled_queries(config):
    """
    Input:
    config - a string for a filename of a json file or dict with
             the required parameters.

    Runs the bash command 'gcloud auth print-access-token' to get the access token, 
    then uses it to enter the BigQuery API via http requests and download all info about
    scheduled queries, in particular their query codes. Saves them to directory specified
    in the config.
    """
    
    # Load config from file:
    if type(config) == str:
        with open(config, 'r') as f:
            config = json.load(f)    

    # Get project_id:
    with open(config['credentials'], 'r') as f:
        credentials = json.load(f)
        project_id  = credentials['project_id']
    
    # Get access token:
    token = check_output(['gcloud', 'auth', 'print-access-token']).decode('utf-8')[:-1]

    # Make HTTP GET of scheduled queries:
    session = requests.Session()
    domain  = 'https://bigquerydatatransfer.googleapis.com'
    session.mount(domain, requests.adapters.HTTPAdapter(max_retries=3))
    url = domain + '/v1/projects/' + project_id + '/transferConfigs?dataSourceIds=scheduled_query'
    # For other data locations rather than US or EU, check:
    # https://stackoverflow.com/questions/55745763/list-scheduled-queries-in-bigquery
    response = session.get(url, headers={'Authorization': 'Bearer ' + token})

    # Get list of scheduled queries:
    sched_raw  = json.loads(response.content)
    sched_list = sched_raw['transferConfigs']
    # Remove disabled (on pause) queries:
    sched_list = list(filter(lambda q: 'disabled' not in q.keys(), sched_list))

    # Delete previously saved views:
    if config['get_scheduled']:
        #print('Deleting old views...')
        del_folder_files(config['scheduled_path'], '.sql')
    
    for s in sched_list:

        # Get query name and destination table name:
        filename           = config['scheduled_path'] + s['displayName'] + '.sql'
        destination_header = '# destination_table: ' + s['destinationDatasetId'] + '.' + \
                             s['params']['destination_table_name_template']
        # Save it to file:
        with open(filename, 'w') as f:
            f.write(destination_header + '\n\n')
            f.write(s['params']['query'])
