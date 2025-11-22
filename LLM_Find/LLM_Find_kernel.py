import LLM_Find_Constants as constants
import LLM_FIND_helper
import os
import requests
import networkx as nx
import pandas as pd
import geopandas as gpd
# from pyvis.network import Network
from openai import OpenAI
import configparser
import pickle
import time
import sys
import traceback

#load config
config = configparser.ConfigParser()
config.read('openai_key_config.ini')

# use your KEY.
OpenAI_key = config.get('API_Key', 'OpenAI_key')
client = OpenAI(api_key=OpenAI_key)

  

class Solution():
    """
    class for the solution. Carefully maintain it.  
    
    by Huan Ning, 2024-04-28
    """
    def __init__(self, 
                 task, 
                 task_name,
                 save_dir,                
                 role=constants.graph_role,
                 model=r"gpt-4o",
                 data_locations=[],
                 stream=True,
                 verbose=True,
                ):        
        self.task = task        
        self.solution_graph = None
        self.graph_response = None
        self.role = role
        self.data_locations=data_locations
        self.task_name = task_name   
        self.save_dir = save_dir
        self.code_for_graph = ""
        self.all_code = ""
        self.graph_file = os.path.join(self.save_dir, f"{self.task_name}.graphml")
        self.source_nodes = None
        self.sink_nodes = None
        self.operations = []  # each operation is an element:
        # {node_name: "", function_descption: "", function_definition:"", return_line:""
        # operation_prompt:"", operation_code:""}
        self.assembly_prompt = ""
        
        self.parent_solution = None
        self.model = model
        self.stream = stream
        self.verbose = verbose

        self.assembly_LLM_response = ""
        self.code_for_assembly = ""
        self.graph_prompt = ""
        self.map_review_comments = ""
          
        self.data_locations_str = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(self.data_locations)])     
        
        graph_requirement = constants.graph_requirement.copy()
        graph_requirement.append(f"Save the network into GraphML format, save it at: {self.graph_file}")
        graph_requirement_str =  '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(graph_requirement)])
        
        graph_prompt = f'Your role: {self.role} \n\n' + \
               f'Your task: {constants.graph_task_prefix} \n {self.task} \n\n' + \
               f'Your reply needs to meet these requirements: \n {graph_requirement_str} \n\n' + \
               f'Your reply example: {constants.graph_reply_exmaple} \n\n' + \
               f'Data locations (each data is a node): {self.data_locations_str} \n'
        self.graph_prompt = graph_prompt
        self.beautify_prompt = ""
        self.map_review_prompt = ""
        self.map_revise_prompt = ""

        # self.direct_request_prompt = ''
        self.direct_request_LLM_response = ''
        self.direct_request_code = ''

        self.chat_history = [{'role': 'system', 'content': role}]

    def get_LLM_reply(self,
            prompt,
            verbose=True,
            temperature=1,
            stream=True,
            retry_cnt=3,
            sleep_sec=10,
            system_role=None,
            model=None,
            ):


        if system_role is None:
            system_role = self.role

        if model is None:
            model = self.model

        # Query ChatGPT with the prompt
        # if verbose:
        #     print("Geting LLM reply... \n")
        count = 0
        isSucceed = False
        self.chat_history.append({'role': 'user', 'content': prompt})
        while (not isSucceed) and (count < retry_cnt):
            try:
                count += 1
                response = client.chat.completions.create(model=model,
                # messages=self.chat_history,  # Too many tokens to run.
                messages=[
                            {"role": "system", "content": system_role},
                            {"role": "user", "content": prompt},
                          ],
                temperature=temperature,
                stream=stream)
            except Exception as e:
                # logging.error(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
                print(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n",
                      e)
                time.sleep(sleep_sec)

        response_chucks = []
        if stream:
            for chunk in response:
                response_chucks.append(chunk)
                content = chunk.choices[0].delta.content
                if content is not None:
                    if verbose:
                        print(content, end='')
        else:
            content = response.choices[0].message.content
            # print(content)
        print('\n\n')
        # print("Got LLM reply.")

        response = response_chucks  # good for saving

        content = helper.extract_content_from_LLM_reply(response)

        self.chat_history.append({'role': 'assistant', 'content': content})

        return response


    @property
    def operation_node_names(self):
        opera_node_names = []
        assert self.solution_graph, "The Soluction class instance has no solution graph. Please generate the graph"
        for node_name in self.solution_graph.nodes():
            node = self.solution_graph.nodes[node_name]
            if node['node_type'] == 'operation':
                opera_node_names.append(node_name)
        return opera_node_names

    def get_ancestor_operations(self, node_name):
        ancestor_operation_names = []
        ancestor_node_names = nx.ancestors(self.solution_graph, node_name)
        # for ancestor_node_name in ancestor_node_names:
        ancestor_operation_names = [node_name for node_name in ancestor_node_names if node_name in self.operation_node_names]

        ancestor_operation_nodes = []
        for oper in self.operations:
            oper_name = oper['node_name']
            if oper_name in ancestor_operation_names:
                ancestor_operation_nodes.append(oper)

        return ancestor_operation_nodes

    def get_descendant_operations(self, node_name):
        descendant__operation_names = []
        descendant_node_names = nx.descendants(self.solution_graph, node_name)
        # for descendant_node_name in descendant_node_names:
        descendant__operation_names = [node_name for node_name in descendant_node_names if node_name in self.operation_node_names]
        # descendant_codes = '\n'.join([oper['operation_code'] for oper in descendant_node_names])
        descendant_operation_nodes = []
        for oper in self.operations:
            oper_name = oper['node_name']
            if oper_name in descendant__operation_names:
                descendant_operation_nodes.append(oper)

        return descendant_operation_nodes

    def get_descendant_operations_definition(self, descendant_operations):

        keys = ['node_name', 'description', 'function_definition', 'return_line']
        operation_def_list = []
        for node in descendant_operations:
            operation_def = {key: node[key] for key in keys}
            operation_def_list.append(str(operation_def))
        defs = '\n'.join(operation_def_list)
        return defs

    def get_prompt_for_an_opearation(self, operation):
        assert self.solution_graph, "Do not find solution graph!"
        # operation_dict = function_def.copy()

        node_name = operation['node_name']

        # get ancestors code
        ancestor_operations = self.get_ancestor_operations(node_name)
        ancestor_operation_codes = '\n'.join([oper['operation_code'] for oper in ancestor_operations])
        descendant_operations = self.get_descendant_operations(node_name)
        descendant_defs = self.get_descendant_operations_definition(descendant_operations)
        descendant_defs_str = str(descendant_defs)

        pre_requirements = [
            f'The function description is: {operation["description"]}',
            f'The function definition is: {operation["function_definition"]}',
            f'The function return line is: {operation["return_line"]}'
        ]

        operation_requirement_str = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(
            pre_requirements + constants.operation_requirement)])

        operation_prompt = f'Your role: {constants.operation_role} \n\n' + \
                           f'operation_task: {constants.operation_task_prefix} {operation["description"]} \n\n' + \
                           f'This function is one step to solve the question/task: {self.task} \n\n' + \
                           f"This function is a operation node in a solution graph for the question/task, the Python code to build the graph is: \n{self.code_for_graph} \n\n" + \
                           f'Data locations: {self.data_locations_str} \n\n' + \
                           f'Your reply example: {constants.operation_reply_exmaple} \n\n' + \
                           f'Your reply needs to meet these requirements: \n {operation_requirement_str} \n\n' + \
                           f"The ancestor function code is (need to follow the generated file names and attribute names): \n {ancestor_operation_codes} \n\n" + \
                           f"The descendant function (if any) definitions for the question are (node_name is function name): \n {descendant_defs_str}"

        operation['operation_prompt'] = operation_prompt
        return operation_prompt



    def prompt_for_assembly_program(self):
        all_operation_code_str = '\n'.join([operation['operation_code'] for operation in self.operations])
        # operation_code = solution.operations[-1]['operation_code']
        # assembly_prompt = f"" + \

        assembly_requirement = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(constants.assembly_requirement)])

        assembly_prompt = f"Your role: {constants.assembly_role} \n\n" + \
                          f"Your task is: use the given Python functions, return a complete Python program to solve the question: \n {self.task}" + \
                          f"Requirement: \n {assembly_requirement} \n\n" + \
                          f"Data location: \n {self.data_locations_str} \n" + \
                          f"Code: \n {all_operation_code_str}"
        
        self.assembly_prompt = assembly_prompt
        return self.assembly_prompt
    
    

    
    def save_solution(self):
#         , graph=True
        new_name = os.path.join(self.save_dir, f"{self.task_name}.pkl")
        with open(new_name, "wb") as f:
            pickle.dump(self, f)

    def get_solution_at_one_time(self):
        pass

    @property
    def direct_request_prompt(self):

        direct_request_requirement_str = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(
            constants.direct_request_requirement)])

        direct_request_prompt = f'Your role: {constants.direct_request_role} \n' + \
                                f'Your task: {constants.direct_request_task_prefix} to address the question or task: {self.task} \n' + \
                           f'Location for data you may need: {self.data_locations_str} \n' + \
                           f'Your reply needs to meet these requirements: \n {direct_request_requirement_str} \n'
        return direct_request_prompt





    def get_debug_prompt(self, exception, code):
        etype, exc, tb = sys.exc_info()
        exttb = traceback.extract_tb(tb)  # Do not quite understand this part.
        # https://stackoverflow.com/questions/39625465/how-do-i-retain-source-lines-in-tracebacks-when-running-dynamically-compiled-cod/39626362#39626362

        ## Fill the missing data:
        exttb2 = [(fn, lnnr, funcname,
                   (code.splitlines()[lnnr - 1] if fn == 'Complete program'
                    else line))
                  for fn, lnnr, funcname, line in exttb]

        # Print:
        error_info_str = 'Traceback (most recent call last):\n'
        for line in traceback.format_list(exttb2[1:]):
            error_info_str += line
        for line in traceback.format_exception_only(etype, exc):
            error_info_str += line

        print(f"Error_info_str: \n{error_info_str}")

        # print(f"traceback.format_exc():\n{traceback.format_exc()}")

        debug_requirement_str = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(constants.debug_requirement)])

        debug_prompt = f"Your role: {constants.debug_role} \n" + \
                          f"Your task: correct the code of a program according to the error information, then return the corrected and completed program. \n\n" + \
                          f"Requirement: \n {debug_requirement_str} \n\n" + \
                          f"The given code is used for this task: {self.task} \n\n" + \
                          f"The data location associated with the given code: \n {self.data_locations_str} \n\n" + \
                          f"The error information for the code is: \n{str(error_info_str)} \n\n" + \
                          f"The code is: \n{code}"

        return debug_prompt












    


    

    
    
    

    
    
    
    