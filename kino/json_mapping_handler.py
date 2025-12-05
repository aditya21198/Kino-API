import os
import json

def json_mapping_handler(type:str,json_file_path=None):
    if json_file_path is None:
        if type =='customer':
            json_file_path = os.path.dirname(os.path.abspath(__file__)) + '/json/customer_code_mapping.json'
        if type =='salesman':
            json_file_path = os.path.dirname(os.path.abspath(__file__)) + '/json/salesman_mapping.json'
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
    
    return config