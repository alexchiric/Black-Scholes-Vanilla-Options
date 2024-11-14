import tempfile
import subprocess
import pandas as pd
import numpy as np
import os

from option_data import get_option_chain, get_last_price



def valuation_pipeline(options_data, contract_symbol, last):

    #Clean data to process as binary file and hold only numeric types
    options_data['optionType'] = options_data['CALL'].apply(lambda x: 1 if x else 0)
    options_data_df = options_data[options_data['contractSymbol'] == contract_symbol]
    options_data_df = options_data_df.drop(columns=['openInterest', 'inTheMoney', 'expirationDate', 'bid', 'ask', 'volume', 'CALL', 'contractSymbol'])
    options_data_df['Underlying'] = last

    #Declare current directory for tempfile
    current_dir = os.getcwd()

    with tempfile.NamedTemporaryFile(delete= False, suffix=".bin", dir=current_dir) as temp_file:
        options_data_np = options_data_df.to_numpy()
        options_data_np.tofile(temp_file.name)
        
        #Rename file in to assure that the CPP file can read it 
        new_file_path = os.path.join(current_dir, 'temp.bin')
        os.rename(temp_file.name, new_file_path)

        #Run command line prompts for the cpp file
        try:
            compile_command = ['clang++', '-o', 'calculation_workflow', 'calculation_workflow.cpp']
            subprocess.run(compile_command)

            run_command = ['./calculation_workflow']
            subprocess.run(run_command)
        except:
            raise RuntimeError("Failed to compile C++ script")
    
    #Remove temp file
    os.remove(new_file_path)

options_data, last = get_option_chain("AAPL"), get_last_price("AAPL")

valuation_pipeline(options_data, 'AAPL241025C00105000', last)