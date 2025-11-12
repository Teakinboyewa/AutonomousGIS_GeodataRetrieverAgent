import io
import json
import re
import sys
import traceback
# import openai
from collections import deque
from openai import OpenAI
from datetime import datetime # NEW CHANGE

import configparser

# import networkx as nx
import logging
import time

import os
import requests
import networkx as nx
import pandas as pd
import geopandas as gpd
from pyvis.network import Network

##>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# Get the directory of the current script
current_script_dir = os.path.dirname(os.path.abspath(__file__))
# Add the directory to sys.path
if current_script_dir not in sys.path:
    sys.path.append(current_script_dir)
import LLM_Find_Constants as constants
import handbook
#<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

class CaseSensitiveConfigParser(configparser.ConfigParser):   # NEW CHANGE
    def optionxform(self, optionstr): # NEW CHANGE
        return optionstr  # Override to preserve case sensitivity # NEW CHANGE

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def load_config():
    config = configparser.ConfigParser()
    # config = CaseSensitiveConfigParser() # NEW CHANGE
    config_path = os.path.join(current_script_dir, 'openai_key_config.ini')
    config.read(config_path)
    return config

# Use the loaded configuration
config = load_config()

# use your KEY.
OpenAI_key = config.get('API_Key', 'OpenAI_key')
client = OpenAI(api_key=OpenAI_key)
#<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

def load_OpenAI_key():
    config = load_config()  # Re-read the configuration file
    OpenAI_key = config.get('API_Key', 'OpenAI_key')
    return OpenAI_key




def create_select_prompt(task):
    select_requirement_str = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(constants.select_requirements)])
    handbook_files = handbook.collect_handbook_files() # NEW CHANGE
    descriptions_str, data_source_dict = handbook.assemble_handbook_description(handbook_files) #NEW CHANGE
    prompt = f"Your role: {constants.select_role} \n" + \
             f"Your mission: {constants.select_task_prefix}: " + f"{task}\n\n" + \
             f"Requirements: \n{select_requirement_str} \n\n" + \
             f"Data sources:{descriptions_str} \n" + \
             f'Your reply example: {constants.selection_reply_example}'

    # print(prompt)

    # The template seems cannot have the "{}", otherwise LangChain may confuse with its variable using "{}" as the tag.

    #     prompt_langChain = ChatPromptTemplate.from_messages([
    #     ("system", constants.select_role),
    #     ("human", prompt)
    # ])

    return prompt

# ***********************************************************************************************************************
# NEW FUNCTIONS
# ************************************************************************************************************************
def select_source(request_id, select_prompt_str, model_name, stream):
    # print("Model Name:", model_name)
    """Return a fine-tuned prompt using the selected model.
        Supports: OpenAI proxy, GPT-5, and normal OpenAI"""
    return unified_llm_call(
        request_id=request_id,
        messages=[
            {"role": "user", "content": select_prompt_str},
        ],
        model_name=model_name,
        stream=stream
    )

def generate_data_fetching_code(request_id, download_prompt_str, model_name, stream):
    # print("Model Name:", model_name)
    """Return a fine-tuned prompt using the selected model.
        Supports: OpenAI proxy, GPT-5, and normal OpenAI"""
    return unified_llm_call(
        request_id=request_id,
        messages=[
            {"role": "user", "content": download_prompt_str},
        ],
        model_name=model_name,
        stream=stream
    )


def get_question_id(user_api_key):
    import requests
    url = f"https://www.gibd.online/api/request-question-id"
    payload = {
            "service_name": "Spatial Data Retrieval Agent",
            "user_api_key": user_api_key}
    response = requests.post(url, json=payload)
    response.text
    return response.json()["question_id"]



def unified_llm_call(request_id, messages, model_name, stream=False, temperature=1, response_format=None, **kwargs):
    import requests
    from LLM_Find_ModelProvider import ModelProviderFactory

    # Check if model requires local provider (Ollama) - this takes precedence
    provider_name = ModelProviderFactory._model_providers.get(model_name, 'openai')

    # Check if using proxy
    api_key = load_OpenAI_key()
    service_name = "Spatial Data Retrieval Agent"

    if provider_name == 'ollama':
        # ===== OLLAMA/LOCAL MODEL CASE - Always use ModelProvider regardless of API key =====
        from LLM_Find_ModelProvider import create_unified_client
        client, provider = create_unified_client(model_name)


        # Use regular completion (Ollama doesn't support structured output via beta API)
        response = provider.generate_completion(
            request_id,
            client,
            model_name,
            messages,
            stream=stream,
            temperature=temperature,
            **kwargs
        )
        return streaming_openai_response(response)


    elif 'gibd-services' in (api_key or ''):
        # ===== PROXY CASE =====
        url = f"https://www.gibd.online/api/openai/{api_key}"
        payload = {
            "service_name": "Spatial Data Retrieval Agent",
            "question_id": request_id,
            "model": model_name,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            **kwargs
        }

        if stream:
            response_req = requests.post(url, json=payload, stream=True)
            # Handle streaming
            def stream_generator():
                for line in response_req.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    delta = chunk['choices'][0].get('delta', {})
                                    content = delta.get('content')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                pass

            # Collect streamed response
            out = ""
            for content in stream_generator():
                print(content, end="")
                out += content

            return out
        else:
            # Non-streaming
            response_req = requests.post(url, json=payload)
            if response_req.status_code == 200:
                data = response_req.json()
                content = data['choices'][0]['message']['content']
                print(content)
                return content
            else:
                print(f"\nError: {response_req.text}")
            # # Clean markdown code blocks if present
            # content = content.strip()
            # if content.startswith('```json'):
            #     content = content[7:]
            # if content.startswith('```'):
            #     content = content[3:]
            # if content.endswith('```'):
            #     content = content[:-3]
            # content = content.strip()
            # return content

    else:
        # ===== NON-PROXY CASE (GPT-5 and Normal OpenAI) =====
        try:
            from LLM_Find_ModelProvider import create_unified_client
            client, provider = create_unified_client(model_name)

            # Check if structured output is requested and supported
            if response_format and client and hasattr(client, 'beta'):
                # Use structured output API
                response = client.beta.chat.completions.parse(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                    **kwargs
                )
                return response.choices[0].message.content
            else:
                # Use regular completion
                response = provider.generate_completion(
                    request_id,
                    client,
                    model_name,
                    messages,
                    stream=stream,
                    temperature=temperature,
                    **kwargs
                )
                return streaming_openai_response(response)

        except ImportError:
            # Direct OpenAI fallback
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            if response_format and hasattr(client, 'beta'):
                # Use structured output
                response = client.beta.chat.completions.parse(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                    **kwargs
                )
                return response.choices[0].message.content
            else:
                # Regular completion
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    stream=stream,
                    temperature=temperature,
                    **kwargs
                )
                return streaming_openai_response(response)


def streaming_openai_response(response):
    # Handle GPT-5 specialized response format first
    if hasattr(response, 'output'):
        # GPT-5 responses.create() format: response.output contains the content
        output = response.output
        if isinstance(output, str):
            return output.strip()
        elif hasattr(output, 'content'):
            return str(output.content).strip()
        else:
            return str(output).strip()

    # Handle GPT-5 alternative format: response.response.body
    if hasattr(response, 'response') and hasattr(response.response, 'body'):
        body = response.response.body
        # Check for choices format in body
        if hasattr(body, 'choices') and body.choices:
            if hasattr(body.choices[0], 'message'):
                content = body.choices[0].message.content
                return content.strip() if isinstance(content, str) else str(content).strip()
        # Check for content attribute in body
        if hasattr(body, 'content'):
            return str(body.content).strip()

    # Streaming case: iterator without .choices
    if hasattr(response, '__iter__') and not hasattr(response, 'choices'):
        out = ""
        for chunk in response:
            # Proxy strings/bytes
            if isinstance(chunk, (str, bytes)):
                t = chunk.decode("utf-8", "ignore") if isinstance(chunk, bytes) else chunk
                if t:
                    print(t, end="")
                    out += t
                continue

            # Try multiple ways to extract content from chunks
            content = None

            # GPT-5 ResponseCreatedEvent format - event-based streaming
            if hasattr(chunk, 'type'):
                try:
                    event_type = getattr(chunk, 'type', '')

                    # GPT-5 output_item events contain the content
                    if 'output_item' in event_type.lower():
                        if hasattr(chunk, 'item'):
                            item = chunk.item

                            # Try to extract text from the item
                            # Method 1: item.content (for text items)
                            if hasattr(item, 'content'):
                                item_content = item.content
                                if isinstance(item_content, str):
                                    content = item_content
                                # Check if content is a list with text parts
                                elif isinstance(item_content, list):
                                    for part in item_content:
                                        if hasattr(part, 'text'):
                                            content = part.text
                                            break
                                        elif isinstance(part, dict) and 'text' in part:
                                            content = part['text']
                                            break

                            # Method 2: item.text (direct text attribute)
                            if not content and hasattr(item, 'text'):
                                content = item.text

                            # Method 3: Try to dump and look for text
                            if not content and hasattr(item, 'model_dump'):
                                try:
                                    item_data = item.model_dump()
                                    if 'content' in item_data:
                                        content = item_data['content']
                                    elif 'text' in item_data:
                                        content = item_data['text']
                                except:
                                    pass

                    # Content delta events contain the actual text
                    elif 'content' in event_type.lower() and 'delta' in event_type.lower():
                        if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'content'):
                            content = chunk.delta.content
                        elif hasattr(chunk, 'content'):
                            content = chunk.content

                    # For done events, check if there's output in response
                    elif event_type == 'response.done':
                        if hasattr(chunk, 'response'):
                            response_obj = chunk.response
                            # Check for output array
                            if hasattr(response_obj, 'output') and response_obj.output:
                                # Output is usually a list of items
                                for output_item in response_obj.output:
                                    if hasattr(output_item, 'content'):
                                        item_content = output_item.content
                                        if isinstance(item_content, str):
                                            content = item_content
                                            break
                                        elif isinstance(item_content, list):
                                            for part in item_content:
                                                if hasattr(part, 'text'):
                                                    content = part.text
                                                    break
                except Exception as e:
                    pass

            # Standard OpenAI ChatCompletionChunk format
            if not content:
                try:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        content = getattr(chunk.choices[0].delta, "content", None)
                except:
                    pass

            # GPT-5 streaming format - check for delta.content directly
            if not content:
                try:
                    if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'content'):
                        content = chunk.delta.content
                except:
                    pass

            # GPT-5 streaming format - check for content attribute directly
            if not content:
                try:
                    if hasattr(chunk, 'content'):
                        content = chunk.content
                except:
                    pass

            # GPT-5 format - check for output in chunk
            if not content:
                try:
                    if hasattr(chunk, 'output'):
                        content = chunk.output
                except:
                    pass

            if content:
                print(content, end="")
                out += str(content)

        print()
        return out

    # Non-streaming case - Standard OpenAI format
    if hasattr(response, "choices"):
        c = getattr(response.choices[0].message, "content", "")
        return c.strip() if isinstance(c, str) else (c or "")

    if isinstance(response, dict):
        c = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return c.strip() if isinstance(c, str) else (c or "")

    return str(response)




def get_openai_key(model_name: str):
    """
    Resolve the OpenAI key for the requested model.
    Uses ModelProvider to determine if the model is local (ollama) or remote.
    For remote models it loads the key from `helper.load_OpenAI_key()`
    and throws a ValueError if none is found.
    """
    try:
        # Import here to avoid import loops if helper.py is imported by other modules
        import LLM_Find_ModelProvider as ModelProvider
        provider_name = ModelProvider.ModelProviderFactory._model_providers.get(model_name, 'openai')
        if provider_name == 'ollama':
            return None  # Local models don't need an OpenAI key
        else:
            OpenAI_key = load_OpenAI_key()
            if not OpenAI_key:
                raise ValueError("Please enter a valid OpenAI API key for this model.")
            return OpenAI_key
    except Exception as e:
        # Fallback: try to load key, but catch errors gracefully
        try:
            return load_OpenAI_key()
        except Exception:
            print(f"Warning: Could not load OpenAI key - {e}")
            return None

def initialize_ai_model(model_name, reasoning_effort_value, OpenAI_key):
    print("=" * 50)
    print("MODEL CONFIGURATION INFO")
    print("=" * 50)
    print(f"Selected Model: {model_name}")

    # Import ModelProvider to determine the correct provider
    try:
        import LLM_Find_ModelProvider as ModelProvider
        from langchain_openai import ChatOpenAI
        provider = ModelProvider.ModelProviderFactory.get_provider(model_name)
        provider_name = ModelProvider.ModelProviderFactory._model_providers.get(model_name, 'openai')

        if model_name == 'gpt-5':
            print("Model Type: GPT-5 (Specialized Provider)")
            reasoning_effort_value = globals().get('reasoning_effort', f'{reasoning_effort_value}')
            print(f"Reasoning Effort: {reasoning_effort_value}")
            print(f"Provider Class: {type(provider).__name__}")
            print(f"Provider Type: Specialized GPT-5 Provider")
            print(f"API Method: client.responses.create() with reasoning parameter")
            print(f"Reasoning Parameter: {{'effort': '{reasoning_effort_value}'}}")

            # Create model and store reasoning effort

            # model = ChatOpenAI(api_key=OpenAI_key, model=model_name, temperature=1)
            model = OpenAI(api_key=OpenAI_key)
            reasoning_effort = reasoning_effort_value

        elif provider_name == 'ollama':
            print(f"Model Type: Local Model via Ollama Provider")
            print(f"Provider Class: {type(provider).__name__}")
            print(f"Provider Type: Ollama Local Provider")
            print(f"API Method: OpenAI-compatible endpoint")
            print(f"Base URL: http://128.118.54.16:11434/v1")

            # Create LangChain ChatOpenAI that points to local server
            from langchain_openai import ChatOpenAI
            # model = ChatOpenAI(
            #     base_url="http://128.118.54.16:11434/v1",
            #     api_key="no-api",
            #     model=model_name,
            #     temperature=1
            # )
            model = OpenAI(
                base_url="http://128.118.54.16:11434/v1",
                api_key="no-api",
            )

        else:
            print("Model Type: Standard OpenAI Model")
            print(f"Provider Class: {type(provider).__name__}")
            print("API Method: client.chat.completions.create()")
            # model = ChatOpenAI(api_key=OpenAI_key, model=model_name, temperature=1)
            model = OpenAI(api_key=OpenAI_key)

    except ImportError as e:
        print(f"WARNING: Could not import ModelProvider: {e}")
        print("Falling back to standard ChatOpenAI")
        # model = ChatOpenAI(api_key=OpenAI_key, model=model_name, temperature=1)
        model = OpenAI(api_key=OpenAI_key)

    # Display API Key status
    if 'gibd-services' in (OpenAI_key or ''):
        # print("API Key: ✓ Loaded (Provided by GIBD-services - http://128.118.54.16:3030/)")
        print("API Key (Provided by GIBD-services): ✓ Loaded")
    elif OpenAI_key:
        print("API Key: ✓ Loaded")
    else:
        print("API Key: Not required")
    return model


# ***********************************************************************************************************************
# NEW FUNCTIONS END
# ************************************************************************************************************************








def convert_chunks_to_str(chunks):
    LLM_reply_str = ""
    for c in chunks:
        # print(c)
        LLM_reply_str += c.content  # c['content']
    return LLM_reply_str


#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def create_download_prompt(task, saved_fname, selected_data_source, handbook_str):
    # select_requirement_str = '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(constants.select_requirements)])
    current_datetime = datetime.now()  # NEW CHANGE
    formatted_datetime = current_datetime.strftime("%Y-%m-%d %H:%M") # NEW CHANGE

    prompt = f"Your role: {constants.download_role} \n" + \
             f"Your mission: {constants.download_task_prefix}: " + f"{task}" + "And set the output file to be:" + f"{saved_fname}\n\n" + \
             f"Data source:{selected_data_source} \n" + \
             f'Your reply example: {constants.download_reply_example}\n' + \
             f"Technical handbook: \n{handbook_str}"

    return prompt
#<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

def get_LLM_reply_LC(
        prompt,
        model,
        verbose=True,
        temperature=1,
        stream=True,
        retry_cnt=3,
        sleep_sec=10,
        system_role="",
):
    """
    Get LLM reply using LangChain. "LC" means LangChain.
    """

    # Query ChatGPT with the prompt
    # if verbose:
    #     print("Geting LLM reply... \n")
    count = 0
    isSucceed = False
    while (not isSucceed) and (count < retry_cnt):
        try:
            count += 1
            # For OpenAI
            if model.dict()["_type"] == "openai-chat":
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
            print(f"Error in get_LLM_reply_LC(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n",
                  e)
            time.sleep(sleep_sec)

    ## Do not know how to process returns of non-OpenAI
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

    # self.chat_history.append({'role': 'assistant', 'content': content})

    return response


def extract_content_from_LLM_reply(response):
    stream = False
    if isinstance(response, list):
        stream = True

    content = ""
    if stream:
        for chunk in response:
            chunk_content = chunk.choices[0].delta.content

            if chunk_content is not None:
                # print(chunk_content, end='')
                content += chunk_content
                # print(content)
        # print()
    else:
        content = response.choices[0].message.content
        # print(content)

    return content


def extract_code(response, verbose=False):
    '''
    Extract python code from reply
    '''
    # if isinstance(response, list):  # use OpenAI stream mode.
    #     reply_content = ""
    #     for chunk in response:
    #         chunk_content = chunk["choices"][0].get("delta", {}).get("content")
    #
    #         if chunk_content is not None:
    #             print(chunk_content, end='')
    #             reply_content += chunk_content
    #             # print(content)
    # else:  # Not stream:
    #     reply_content = response["choices"][0]['message']["content"]

    python_code = ""
    reply_content = extract_content_from_LLM_reply(response)
    python_code_match = re.search(r"```(?:python)?(.*?)```", reply_content, re.DOTALL)
    if python_code_match:
        python_code = python_code_match.group(1).strip()

    if verbose:
        print(python_code)

    return python_code


def extract_code_from_str(LLM_reply_str, verbose=False):
    '''
    Extract python code from reply string, not 'response'.
    '''

    python_code = ""
    python_code_match = re.search(r"```(?:python)?(.*?)```", LLM_reply_str, re.DOTALL)
    if python_code_match:
        python_code = python_code_match.group(1).strip()

    if verbose:
        print(python_code)

    return python_code

# ***********************************************************************************************************************
# NEW FUNCTIONS
# ************************************************************************************************************************
def execute_complete_program(request_id, code: str, try_cnt: int, task: str, model_name: str, handbook_str: str, stream) -> str:
    count = 0
    output_capture = io.StringIO()
    original_stdout = sys.stdout  # Save the original stdout

    error_collector = []
    # Generate unique request ID to track all attempts for this user request
    # import uuid
    # request_id = str(uuid.uuid4())
    # print(f"REQUEST_ID:{request_id}")  # Use parseable format for UI to capture


    while count < try_cnt:
        print(f"\n\n-------------- Running code (trial # {count + 1}/{try_cnt}) --------------\n\n")
        try:
            count += 1
            # Redirect stdout to capture print output
            sys.stdout = output_capture

            compiled_code = compile(code, 'Complete program', 'exec')
            exec(compiled_code, globals())  # #pass only globals() not locals()
            # !!!!    all variables in code will become global variables! May cause huge issues!     !!!!

            # Restore original stdout after execution
            sys.stdout = original_stdout

            # Display the successfully executed code
            print("\nSuccessfully executed code:")
            print("```python")
            print(code)
            print("```")
            # print("\n\n--------------- Done ---------------\n\n")

            # send_error(user_api_key=load_OpenAI_key(), request_id=request_id, user_query=task, feedback="", feedback_message ="", error_msg ="", error_traceback="", generated_code=code)
            return code, error_collector

        # except SyntaxError as err:
        #     error_class = err.__class__.__name__
        #     detail = err.args[0]
        #     line_number = err.lineno
        #
        except Exception as err:
            sys.stdout = original_stdout  # Restore original stdout in case of error
            error_traceback = traceback.format_exc()
            error_collector.append({"attempt": count,
                                    "code_snapshot": code[:800],  # truncate long code
                                    "error_message": str(err),
                                    "error_traceback": error_traceback
                                    })
            # cl, exc, tb = sys.exc_info()

            # print("An error occurred: ", traceback.extract_tb(tb))
            #

            if count == try_cnt:
                print(f"Failed to execute and debug the code within {try_cnt} times.")
                return code, error_collector

            # print("code in execute_complete_program():", code)
            #
            debug_prompt = get_debug_prompt(exception=err, code=code, task=task, handbook_str=handbook_str)
            print("=" * 50)
            print("AI IS DEBUGGING THE CODE...")
            print("=" * 50)
            # print("Sending error information to LLM for debugging...")
            # print("Prompt:\n", debug_prompt)

            # Format the debug prompt like other prompts
            formatted_debug_prompt = f"{constants.debug_role}\n\n{debug_prompt}"

            # Use the same successful streaming method as code generation
            print("DEBUGGING RESPONSE:", end="", flush=True)

            try:
                debug_response_str =  unified_llm_call(
                    request_id=request_id,
                    messages=[
                        {"role": "system", "content": formatted_debug_prompt},
                    ],
                    model_name=model_name,
                    stream=stream
                )
            except Exception as e:
                print(f"\n\nError:{e}")
                print(f"Retrying with same code (attempt {count}/{try_cnt})...")
                continue

            # code = extract_code(debug_response_str)
            code =extract_code_from_str(debug_response_str)

            # Emit the debugged code to the UI
            # print("DEBUGGING COMPLETED - SENDING CODE TO UI", flush=True)
            print("=" * 50, flush=True)
            print("\nDEBUGGED CODE:")
            print("```python")
            print(code)
            print("```")

            import urllib.parse
            print("CODE_READY_URLENCODED:" + urllib.parse.quote(code), flush=True)

            # Capture full traceback for error reporting
            # error_traceback = traceback.format_exc()
            # send_error(developer_api_key=load_OpenAI_key(), user_api_key=load_OpenAI_key(), user_query=task, feedback= code, error_msg=error_traceback, request_id=request_id, attempt_number=count, status="error")
            # send_error(user_api_key=load_OpenAI_key(), request_id=request_id, user_query=task, feedback="",
            #            feedback_message="", error_msg=str(err), error_traceback=error_traceback, generated_code=code)

            sys.stdout.flush()  # Force flush to ensure output reaches UI

    return code,error_collector


# def send_error(user_api_key, request_id, user_query, feedback, feedback_message, error_msg, error_traceback, generated_code):
#
#     # Only send error reports if using gibd-services API key
#     if 'gibd-services' not in (user_api_key or ''):
#         # Return a mock response object for compatibility
#         class MockResponse:
#             status_code = 200
#             text = "Error reporting skipped (not using gibd-services API key)"
#             def json(self):
#                 return {}
#         return MockResponse()
#
#     url = f"https://www.gibd.online/api/feedback/{user_api_key}"
#
#     # Data to send
#     data = {
#         "service": "Spatial Data Retrieval Agent",
#         "requestID": request_id,
#         "question": user_query,
#         "feedback": feedback,
#         "feedback_message": feedback_message,
#         "error": str(error_msg),  # Convert error to string for JSON serialization
#         "error_msg": error_msg,
#         "error_traceback": error_traceback,
#         "generated_code": generated_code
#     }
#     # Send POST request
#     response = requests.post(
#         url,
#         headers={"Content-Type": "application/json"},
#         json=data
#     )
#     return response





# ***********************************************************************************************************************
# NEW FUNCTIONS END
# ************************************************************************************************************************
# def execute_complete_program(code: str, try_cnt: int, task: str, model_name: str, handbook_str: str) -> str:
#     count = 0
#     while count < try_cnt:
#         print(f"\n\n-------------- Running code (trial # {count + 1}/{try_cnt}) --------------\n\n")
#         try:
#             count += 1
#             compiled_code = compile(code, 'Complete program', 'exec')
#             exec(compiled_code, globals())  # #pass only globals() not locals()
#             # !!!!    all variables in code will become global variables! May cause huge issues!     !!!!
#             print("\n\n--------------- Done ---------------\n\n")
#             return code
#
#         # except SyntaxError as err:
#         #     error_class = err.__class__.__name__
#         #     detail = err.args[0]
#         #     line_number = err.lineno
#         #
#         except Exception as err:
#
#             # cl, exc, tb = sys.exc_info()
#
#             # print("An error occurred: ", traceback.extract_tb(tb))
#             #
#
#             if count == try_cnt:
#                 print(f"Failed to execute and debug the code within {try_cnt} times.")
#                 return code
#
#             # print("code in execute_complete_program():", code)
#             #
#             debug_prompt = get_debug_prompt(exception=err, code=code, task=task, handbook_str=handbook_str)
#             print("Sending error information to LLM for debugging...")
#             # print("Prompt:\n", debug_prompt)
#             response = get_LLM_reply(prompt=debug_prompt,
#                                      system_role=constants.debug_role,
#                                      model=model_name,
#                                      verbose=True,
#                                      stream=True,
#                                      retry_cnt=5,
#                                      )
#             code = extract_code(response)
#
#     return code


def get_debug_prompt(exception, code, task, handbook_str):
    etype, exc, tb = sys.exc_info()
    exttb = traceback.extract_tb(tb)  # Do not quite understand this part.
    # https://stackoverflow.com/questions/39625465/how-do-i-retain-source-lines-in-tracebacks-when-running-dynamically-compiled-cod/39626362#39626362

    print("code in get_debug_prompt:", code)
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
                   f"The given code is used for this task: {task} \n\n" + \
                   f"The technical guidelines for the code: \n {handbook_str} \n\n" + \
                   f"The error information for the code is: \n{str(error_info_str)} \n\n" + \
                   f"The code is: \n{code}"

    return debug_prompt


def get_LLM_reply(prompt="Provide Python code to read a CSV file from this URL and store the content in a variable. ",
                  system_role=r'You are a professional Geo-information scientist and developer.',
                  model=r"gpt-3.5-turbo",
                  verbose=True,
                  temperature=1,
                  stream=True,
                  retry_cnt=3,
                  sleep_sec=10,
                  ):
    # Generate prompt for ChatGPT
    # url = "https://github.com/gladcolor/LLM-Geo/raw/master/overlay_analysis/NC_tract_population.csv"
    # prompt = prompt + url

    # Query ChatGPT with the prompt
    # if verbose:
    #     print("Geting LLM reply... \n")
    count = 0
    isSucceed = False
    while (not isSucceed) and (count < retry_cnt):
        try:
            count += 1
            response = client.chat.completions.create(model=model,
                                                      messages=[
                                                          {"role": "system", "content": system_role},
                                                          {"role": "user", "content": prompt},
                                                      ],
                                                      temperature=temperature,
                                                      stream=stream)
        except Exception as e:
            # logging.error(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
            print(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
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

    return response


def get_LLM_reply_v0(
        prompt="Provide Python code to read a CSV file from this URL and store the content in a variable. ",
        system_role=r'You are a professional Geo-information scientist and developer.',
        model=r"gpt-3.5-turbo",
        verbose=True,
        temperature=1,
        stream=True,
        retry_cnt=3,
        sleep_sec=10,
        ):
    # Generate prompt for ChatGPT
    # url = "https://github.com/gladcolor/LLM-Geo/raw/master/overlay_analysis/NC_tract_population.csv"
    # prompt = prompt + url

    # Query ChatGPT with the prompt
    # if verbose:
    #     print("Geting LLM reply... \n")
    count = 0
    isSucceed = False
    while (not isSucceed) and (count < retry_cnt):
        try:
            count += 1
            response = client.chat.completions.create(model=model,
                                                      messages=[
                                                          {"role": "system", "content": system_role},
                                                          {"role": "user", "content": prompt},
                                                      ],
                                                      temperature=temperature,
                                                      stream=stream)
        except Exception as e:
            # logging.error(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
            print(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
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

    return response


def get_LLM_vision_reply(
        prompt="Provide Python code to read a CSV file from this URL and store the content in a variable. ",
        system_role=r'You are a professional Geo-information scientist and developer.',
        model=r"gpt-3.5-turbo",
        img_base64="",
        verbose=True,
        temperature=1,
        stream=True,
        retry_cnt=3,
        sleep_sec=10,
        ):
    # Generate prompt for ChatGPT
    # url = "https://github.com/gladcolor/LLM-Geo/raw/master/overlay_analysis/NC_tract_population.csv"
    # prompt = prompt + url

    # Query ChatGPT with the prompt
    # if verbose:
    #     print("Geting LLM reply... \n")
    count = 0
    isSucceed = False
    while (not isSucceed) and (count < retry_cnt):
        try:
            count += 1
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system", "content": system_role
                    },

                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64, {img_base64}",
                                    # "detail": "high"
                                }  # This closing brace matches the "image_url" dictionary
                            }
                        ],

                    },
                ],
                temperature=temperature,
                stream=stream
            )

        except Exception as e:
            # logging.error(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
            print(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
            time.sleep(sleep_sec)

    response_chucks = []
    # response_chucks = ""
    if stream:
        for chunk in response:
            response_chucks.append(chunk)
            content = chunk.choices[0].delta.content
            if content is not None:
                # response_chucks += str(content)
                if verbose:
                    print(content, end='')


    else:
        content = response.choices[0].message.content
        # response_chucks += content
        # print(content)
    print('\n\n')
    # print("Got LLM reply.")

    # response = response_chucks # good for saving

    return response_chucks


def has_disconnected_components(directed_graph, verbose=True):
    # Get the weakly connected components
    weakly_connected = list(nx.weakly_connected_components(directed_graph))

    # Check if there is more than one weakly connected component
    if len(weakly_connected) > 1:
        if verbose:
            print("component count:", len(weakly_connected))
        return True
    else:
        return False


def generate_function_def(node_name, G):
    '''
    Return a dict, includes two lines: the function definition and return line.
    parameters: operation_node
    '''
    node_dict = G.nodes[node_name]
    node_type = node_dict['node_type']

    predecessors = G.predecessors(node_name)

    # print("predecessors:", list(predecessors))

    # create parameter list with default values
    para_default_str = ''  # for the parameters with the file path
    para_str = ''  # for the parameters without the file path
    for para_name in predecessors:
        # print("para_name:", para_name)
        para_node = G.nodes[para_name]
        # print(f"para_node: {para_node}")
        # print(para_node)
        data_path = para_node.get('data_path', '')  # if there is a path, the function need to read this file

        if data_path != "":
            para_default_str = para_default_str + f"{para_name}='{data_path}', "
        else:
            para_str = para_str + f"{para_name}={para_name}, "

    all_para_str = para_str + para_default_str

    function_def = f'{node_name}({all_para_str})'
    function_def = function_def.replace(', )', ')')  # remove the last ","

    # generate the return line
    successors = G.successors(node_name)
    return_str = 'return ' + ', '.join(list(successors))

    # print("function_def:", function_def)  # , f"node_type:{node_type}"
    # print("return_str:", return_str)  # , f"node_type:{node_type}"
    # print(function_def, predecessors, successors)
    return_dict = {"function_definition": function_def,
                   "return_line": return_str,
                   'description': node_dict['description'],
                   'node_name': node_name
                   }
    return return_dict


def bfs_traversal(graph, start_nodes):
    visited = set()
    queue = deque(start_nodes)

    order = []
    while queue:
        node = queue.popleft()
        # print(node)
        if node not in visited:
            order.append(node)
            visited.add(node)
            queue.extend(neighbor for neighbor in graph[node] if neighbor not in visited)
    return order


def generate_function_def_list(G):
    '''
    Return a list, each string is the function definition and return line
    '''
    # start with the data loading, following the data flow.
    nodes = []
    # Find nodes without predecessors
    nodes_without_predecessors = [node for node in G.nodes() if G.in_degree(node) == 0]
    # print(nodes_without_predecessors)
    # Traverse the graph using BFS starting from the nodes without predecessors
    traversal_order = bfs_traversal(G, nodes_without_predecessors)

    # print("traversal_order:", traversal_order)

    def_list = []
    data_node_list = []
    for node_name in traversal_order:
        node_type = G.nodes[node_name]['node_type']
        if node_type == 'operation':
            # print(node_name, node_type)
            # predecessors = G.predecessors('Load_shapefile')
            # successors = G.successors('Load_shapefile')

            function_def_returns = generate_function_def(node_name, G)
            def_list.append(function_def_returns)

        if node_type == 'data':
            data_node_list.append(node_name)

    return def_list, data_node_list


def get_given_data_nodes(G):
    given_data_nodes = []
    for node_name in G.nodes():
        node = G.nodes[node_name]
        in_degrees = G.in_degree(node_name)
        if in_degrees == 0:
            given_data_nodes.append(node_name)
            # print(node_name,in_degrees,  node)
    return given_data_nodes


def get_data_loading_nodes(G):
    data_loading_nodes = set()

    given_data_nodes = get_given_data_nodes(G)
    for node_name in given_data_nodes:

        successors = G.successors(node_name)
        for node in successors:
            data_loading_nodes.add(node)
            # print(node_name,in_degrees,  node)
    data_loading_nodes = list(data_loading_nodes)
    return data_loading_nodes


def get_data_sample_text(file_path, file_type="csv", encoding="utf-8"):
    """
    file_type: ["csv", "shp", "txt"]
    return: a text string
    """
    if file_type == "csv":
        df = pd.read_csv(file_path)
        text = str(df.head(3))

    if file_type == "shp":
        gdf = gpd.read_file(file_path)
        text = str(gdf.head(2))  # .drop('geomtry')

    if file_type == "txt":
        with open(file_path, 'r', encoding=encoding) as f:
            lines = f.readlines()
            text = ''.join(lines[:3])
    return text


def show_graph(G):
    if has_disconnected_components(directed_graph=G):
        print("Disconnected component, please re-generate the graph!")

    nt = Network(notebook=True,
                 cdn_resources="remote",
                 directed=True,
                 # bgcolor="#222222",
                 # font_color="white",
                 height="800px",
                 # width="100%",
                 #  select_menu=True,
                 # filter_menu=True,

                 )

    nt.from_nx(G)

    sinks = find_sink_node(G)
    sources = find_source_node(G)
    # print("sinks:", sinks)

    # Set node colors based on node type
    node_colors = []
    for node in nt.nodes:
        # print('node:', node)
        if node['node_type'] == 'data':
            # print('node:', node)
            if node['label'] in sinks:
                node_colors.append('violet')  # lightgreen
                # print(node)
            elif node['label'] in sources:
                node_colors.append('lightgreen')  #
                # print(node)
            else:
                node_colors.append('orange')

        elif node['node_type'] == 'operation':
            node_colors.append('deepskyblue')

            # Update node colorsb
    for i, color in enumerate(node_colors):
        nt.nodes[i]['color'] = color
        # nt.nodes[i]['shape'] = 'box'
        nt.nodes[i]['shape'] = 'dot'
        # nt.set_node_style(node, shape="box")

    return nt


def find_sink_node(G):
    """
    Find the sink node in a NetworkX directed graph.

    :param G: A NetworkX directed graph
    :return: The sink node, or None if not found
    """
    sinks = []
    for node in G.nodes():
        if G.out_degree(node) == 0 and G.in_degree(node) > 0:
            sinks.append(node)
    return sinks


# Function to find the source node
def find_source_node(graph):
    # Initialize an empty list to store potential source nodes
    source_nodes = []

    # Iterate over all nodes in the graph
    for node in graph.nodes():
        # Check if the node has no incoming edges
        if graph.in_degree(node) == 0:
            # Add the node to the list of source nodes
            source_nodes.append(node)

    # Return the source nodes
    return source_nodes

