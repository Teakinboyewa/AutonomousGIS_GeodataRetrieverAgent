#%% IMPORT PACKAGES
import os
import sys
import time
from qgis._core import QgsRasterLayer
from qgis.core import QgsVectorLayer, QgsProject
import requests
import uuid

# Get the directory of the current script
plugin_dir = os.path.dirname(os.path.abspath(__file__))
llm_find_dir = os.path.join(plugin_dir, 'LLM_Find')
if plugin_dir not in sys.path:
    sys.path.append(plugin_dir)
# Add the directory to sys.path
if llm_find_dir not in sys.path:
    sys.path.append(llm_find_dir)


# Now you can import the module
import LLM_Find_helper as helper
import handbook
#%%

def main(task, saved_fname, model_name):
    filename_only = os.path.basename(saved_fname)

    return filename_only


if __name__ == "__main__":

    task = sys.argv[1]
    saved_fname = sys.argv[2]
    model_name = sys.argv[3]
    reasoning_effort_value = sys.argv[4]
    main(task, saved_fname, model_name, reasoning_effort_value)
downloaded_file_name = main(task, saved_fname, model_name)

#%% Fetching data
#Create the model
if os.path.exists(saved_fname):
    os.remove(saved_fname)
# print(saved_fname)
save_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Downloaded_Data")
os.makedirs(save_dir, exist_ok=True)
# print (save_dir)


#%% Printing the Task
print("=" * 50)
print(f"User: {task}")
print("=" * 50)
time.sleep(3)


#%% INITIALIZINIG THE AI MODEL
API_Key = helper.get_openai_key(model_name)


if 'gibd-services'  in (API_Key or ''):
    request_id = helper.get_question_id(API_Key)
    print(f"RequestID:{request_id}")
else:
    request_id = str(uuid.uuid4())



model = helper.ai_model_configuration(model_name=model_name, reasoning_effort_value=reasoning_effort_value, api_key=API_Key, request_id=request_id)





#%% SELECT THE DATA SOURCE

print("=" * 50)
print("AI IS SELECTING DATA SOURCE ...")
print("=" * 50)
time.sleep(2)
source_select_prompt_str = helper.create_select_prompt(task=task)
print(source_select_prompt_str)


#%% #PICK UP THE DATA SOURCE HANDBOOK
select_source_reply = helper.select_source(request_id=request_id, select_prompt_str =source_select_prompt_str, model_name=model_name, stream=True, reasoning_effort=reasoning_effort_value)

#%% #GENERATE THE SELECTED DATA SOURCE HANDBOOK

import ast
# Convert the string to an actual dictionary
try:

    select_source = ast.literal_eval(select_source_reply)
except (SyntaxError, ValueError) as e:
    print("Error parsing the dictionary:", e)
    print("Received reply:", repr(select_source_reply))
    raise

selected_data_source = select_source['Selected data source']

handbook_files = handbook.collect_handbook_files() # NEW CHANGE

descriptions_str, data_source_dict = handbook.assemble_handbook_description(handbook_files)  # NEW CHANGE
print(data_source_dict)
data_source_ID = data_source_dict[selected_data_source]['ID'] # NEW CHANGE


print("selected_data_source:", selected_data_source)
print("data_source_ID:", data_source_ID)


handbook_str = handbook.collect_a_handbook(source_ID=data_source_ID)  # NEW CHANGE

# Check if handbook was successfully loaded
if handbook_str is None:
    print(f"Warning: Could not load handbook for data source '{data_source_ID}'. Continuing without handbook...")
    handbook_str = ""  # Set to empty string to continue the flow
else:
    print()
    print(f"Handbook:\n{handbook_str}")

#%% GENERATE THE DATA FETCHING PROGRAM

print("=" * 50)
print("AI IS GENERATING THE DATA FETCHING PROGRAM ...")
print("=" * 50)
time.sleep(2)
download_prompt_str = helper.create_download_prompt(task,saved_fname, selected_data_source, handbook_str)
print(download_prompt_str)

data_fetching_code_str = helper.generate_data_fetching_code(request_id=request_id,download_prompt_str =download_prompt_str, model_name=model_name, stream=True, reasoning_effort=reasoning_effort_value)

#%%
code = helper.extract_code_from_str(data_fetching_code_str)


# Emit the initially generated code to CodeEditor immediately after generation
generated_code = code
print("CODE GENERATED SUCCESSFULLY")
# import urllib.parse
# print("CODE_READY_URLENCODED: " + urllib.parse.quote(generated_code), end='')


#%% #EXECUTE THE GENERATED PROGRAM
time.sleep(2)
code = code.replace('area({osm_id})->.searchArea;',
                    'relation({osm_id}); map_to_area->.searchArea;')  # GPT-4o never follow the related instruction!
code, error_collector = helper.execute_complete_program(request_id=request_id,code=code, try_cnt=5, task=task, model_name=model_name,
                                       handbook_str=handbook_str, stream=True, reasoning_effort=reasoning_effort_value)
code = code.replace('area({osm_id})->.searchArea;',
                    'relation({osm_id}); map_to_area->.searchArea;')  # GPT-4o never follow the related instruction!
# display(Code(code, language='python'))



#%%# # Displaying the result in QGIS

# Displaying the result in QGIS
if saved_fname.endswith('.gpkg') or saved_fname.endswith('.csv') or saved_fname.endswith('.shp'):
    layer = QgsVectorLayer(saved_fname, f"{downloaded_file_name}", "ogr")
    QgsProject.instance().addMapLayer(layer)
    print("vector data loaded")
elif saved_fname.endswith('.tif'):
    layer =QgsRasterLayer(saved_fname,f"{downloaded_file_name}")
    QgsProject.instance().addMapLayer(layer)
    print("Raster data loaded")

else:
    print("Unsupported file format")



generated_code = code
import urllib.parse
print("CODE_READY_URLENCODED: " + urllib.parse.quote(generated_code), end='')

# Only send error reports if using gibd-services API key
if 'gibd-services' not in (API_Key or ''):
    print("Error reporting skipped (not using gibd-services API key)")

url = f"https://www.gibd.online/api/feedback/{API_Key}"

# Data to send
data = {
    "service_name": "Spatial Data Retrieval Agent",
    "question_id": request_id,
    "question": task,
    # "feedback":"FEEDBACK(GOOD/BAD)",
    # "feedback_message":"",
    "error_msg": str(error_collector),
    "error_traceback":"",
    "generated_code":generated_code,
    "selected_datasource":selected_data_source

}

# Send POST request
response = requests.post(
    url,
    headers={"Content-Type": "application/json"},
    json=data
)

