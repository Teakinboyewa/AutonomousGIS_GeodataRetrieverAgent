#%% IMPORTS
import io
import json
import re
import sys
import traceback
from openai import OpenAI
from datetime import datetime # NEW CHANGE
import configparser
import os
import requests
import urllib.parse

# Get the directory of the current script
current_script_dir = os.path.dirname(os.path.abspath(__file__))
# Add the directory to sys.path
if current_script_dir not in sys.path:
    sys.path.append(current_script_dir)
import LLM_Find_Constants as constants
import handbook

from LLM_Find_ModelProvider import ModelProviderFactory
from LLM_Find_ModelProvider import create_unified_client
import LLM_Find_ModelProvider as ModelProvider
#%%

class CaseSensitiveConfigParser(configparser.ConfigParser):   # NEW CHANGE
    def optionxform(self, optionstr): # NEW CHANGE
        return optionstr  # Override to preserve case sensitivity # NEW CHANGE


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
    return prompt


def ai_model_configuration(model_name, reasoning_effort_value, api_key, request_id):
    print("=" * 50)
    print("MODEL CONFIGURATION INFO")
    print("=" * 50)
    print(f"Selected Model: {model_name}")
    try:

        provider = ModelProvider.ModelProviderFactory.get_provider(model_name)
        provider_name = ModelProvider.ModelProviderFactory._model_providers.get(model_name, 'openai')

        if model_name in ['gpt-5', 'gpt-5.1']:
            reasoning_effort = reasoning_effort_value
            # reasoning_effort = globals().get('reasoning_effort', f'{reasoning_effort_value}')
            # print(f"Reasoning Effort: {reasoning_effort}")
            print(f"Reasoning Parameter: {{'effort': '{reasoning_effort}'}}")
            print(f"Provider Class: {type(provider).__name__}")
            print(f"Provider Type: Specialized GPT5 Provider")
            print(f"API Method: client.responses.create() with reasoning parameter")
            model = OpenAI(api_key=api_key)

        elif provider_name == 'ollama':
            print(f"Model Type: Local Model via Ollama Provider")
            print(f"Provider Class: {type(provider).__name__}")
            print(f"Provider Type: Ollama Local Provider")
            print(f"API Method: OpenAI-compatible endpoint")
            print(f"Base URL: http://128.118.54.16:11434/v1")
            model = OpenAI(
                base_url="http://128.118.54.16:11434/v1",
                api_key="no-api",
            )

        else:
            print("Model Type: Standard OpenAI Model")
            print(f"Provider Class: {type(provider).__name__}")
            print("API Method: client.chat.completions.create()")
            model = OpenAI(api_key=api_key)

    except ImportError as e:
        print(f"WARNING: Could not import ModelProvider: {e}")
        print("Falling back to standard OpenAI")
        model = OpenAI(api_key=api_key)

    # Display API Key status
    if 'gibd-services' in (api_key or ''):
        # print("API Key: ✓ Loaded (Provided by GIBD-services - http://128.118.54.16:3030/)")
        print("API Key (Provided by GIBD-services)): ✓  GIBD API Key Loaded")
        print(f"Request ID:{request_id}")
    elif api_key:
        print("API Key: ✓ OpenAI API Key Loaded")
    else:
        print("API Key: Not required")
    return model




def select_source(request_id, select_prompt_str, model_name, stream, reasoning_effort=None):

    """Return a fine-tuned prompt using the selected model.
        Supports: OpenAI proxy, GPT-5, and normal OpenAI"""
    if reasoning_effort:
        print(f"[DEBUG] select_source: reasoning_effort = {reasoning_effort}")

    kwargs = {}
    # Only pass reasoning_effort for GPT-5 models
    if reasoning_effort and model_name in ['gpt-5', 'gpt-5.1']:
        kwargs['reasoning_effort'] = reasoning_effort
        print(f"[DEBUG] select_source: reasoning_effort ENABLED for {model_name}")
    elif reasoning_effort:
        print(f"[DEBUG] select_source: reasoning_effort IGNORED for {model_name} (not supported)")

    return unified_llm_call(
        request_id=request_id,
        messages=[
            {"role": "user", "content": select_prompt_str},
        ],
        model_name=model_name,
        stream=stream,
        **kwargs
    )

def generate_data_fetching_code(request_id, download_prompt_str, model_name, stream, reasoning_effort=None):

    """Return a fine-tuned prompt using the selected model.
        Supports: OpenAI proxy, GPT-5, and normal OpenAI"""
    # if reasoning_effort:
        # print(f"[DEBUG] generate_data_fetching_code: reasoning_effort = {reasoning_effort}")

    kwargs = {}
    # Only pass reasoning_effort for GPT-5 models
    if reasoning_effort and model_name in ['gpt-5', 'gpt-5.1']:
        kwargs['reasoning_effort'] = reasoning_effort
        # print(f"[DEBUG] generate_data_fetching_code: reasoning_effort ENABLED for {model_name}")
    # elif reasoning_effort:
    #     print(f"[DEBUG] generate_data_fetching_code: reasoning_effort IGNORED for {model_name} (not supported)")

    return unified_llm_call(
        request_id=request_id,
        messages=[
            {"role": "user", "content": download_prompt_str},
        ],
        model_name=model_name,
        stream=stream,
        **kwargs
    )


def get_question_id(user_api_key):
    url = f"https://www.gibd.online/api/request-question-id"

    payload = {
            "service_name": "Spatial Data Retrieval Agent",
            "user_api_key": user_api_key}

    response = requests.post(url, json=payload)
    # response.text
    if response.status_code == 201:
        return response.json()["question_id"]
    else:
        error_msg = f"Error {response.status_code}: {response.text}"
        print(error_msg)
        raise Exception(error_msg)  # This will terminate execution


        # return None
    # if response.status_code == 200:
    #     return response.json()["question_id"]
    # else:
    #     print(f"Error {response.status_code}: {response.text}")
    #     return None  # or raise an exception
    #
    # response.text
    # return response.json()["question_id"]



def unified_llm_call(request_id, messages, model_name, stream=False, temperature=1, response_format=None, **kwargs):
    # Debug: Check if reasoning_effort is in kwargs
    # if 'reasoning_effort' in kwargs:
        # print(f"[DEBUG] unified_llm_call: reasoning_effort = {kwargs['reasoning_effort']}")

    # Check if model requires local provider (Ollama) - this takes precedence
    provider_name = ModelProviderFactory._model_providers.get(model_name, 'openai')

    # Check if using proxy
    api_key = load_OpenAI_key()
    service_name = "Spatial Data Retrieval Agent"

    if provider_name == 'ollama':
        # ===== OLLAMA/LOCAL MODEL CASE - Always use ModelProvider regardless of API key =====
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

    elif provider_name == 'gpt5':
        # GPT5 - API key required
        if not api_key:
            raise ValueError("API key required for GPT5 provider")
        # ===== PROXY CASE =====
        if 'gibd-services' in (api_key or ''):
            # Use GIBD proxy service
            return GIBD_Service_call(api_key, service_name, request_id=request_id, model_name=model_name, messages=messages, stream=stream, temperature=temperature, **kwargs)

        else:
            # ===== NON-PROXY CASE (GPT-5 and Normal OpenAI) =====
            try:
                client, provider = create_unified_client(model_name)

                # Check if structured output is requested and supported
                if response_format and client and hasattr(client, 'beta'):
                    # Use structured output API
                    # print("[DEBUG PRINT]: Using structured output API for chat completion")
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
                    # print("[DEBUG PRINT]: Using customized regular completion (streaming_openai_response)")
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
                # print("[DEBUG PRINT]: Using Direct OpenAI fallback for completion")
                client = OpenAI(api_key=api_key)

                if response_format and hasattr(client, 'beta'):
                    # print("[DEBUG PRINT]: Using beta response format")
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
                    # print("[DEBUG PRINT]: Using non-beta response format")
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        stream=stream,
                        temperature=temperature,
                        **kwargs
                    )
                    return streaming_openai_response(response)



    else:
        # OpenAI - API key required
        if not api_key:
            raise ValueError("API key required for OpenAI provider")



        if 'gibd-services' in (api_key or ''):
        # if api_key.startswith('gibd-services'):
            # Use GIBD proxy service
            return GIBD_Service_call(api_key, service_name, request_id=request_id,
                                     model_name=model_name, messages=messages,
                                     stream=stream, temperature=temperature, **kwargs)
        else:
            # print("[DEBUG PRINT]: Using OpenAI model")

            client = OpenAI(api_key=api_key)

            if response_format and hasattr(client, 'beta'):
                # print("[DEBUG PRINT]: Using beta response format")
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
                # print("[DEBUG PRINT]: Using non-beta response format")
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    stream=stream,
                    temperature=temperature,
                    **kwargs
                )
                return streaming_openai_response(response)

def GIBD_Service_call(api_key, service_name, request_id, model_name, messages, stream, temperature, **kwargs ):

        url = f"https://www.gibd.online/api/openai/{api_key}"
        payload = {
            "service_name": service_name,
            "question_id": request_id,
            "model": model_name,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            **kwargs
        }

        if stream:
            # print("[DEBUG PRINT]: Using streaming GIBD API")
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
            # print("[DEBUG PRINT]: Using Non streaming GIBD API")
            # Non-streaming
            response_req = requests.post(url, json=payload)
            if response_req.status_code == 200:
                data = response_req.json()
                content = data['choices'][0]['message']['content']
                print(content)
                return content
            else:
                print(f"\nError: {response_req.text}")



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





def convert_chunks_to_str(chunks):
    LLM_reply_str = ""
    for c in chunks:
        # print(c)
        LLM_reply_str += c.content  # c['content']
    return LLM_reply_str

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


def execute_complete_program(request_id, code: str, try_cnt: int, task: str, model_name: str, handbook_str: str, stream, reasoning_effort=None) -> str:
    # if reasoning_effort:
    #     print(f"[DEBUG] execute_complete_program: reasoning_effort = {reasoning_effort}")

    count = 0
    output_capture = io.StringIO()
    original_stdout = sys.stdout  # Save the original stdout

    error_collector = []


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

            return code, error_collector


        except Exception as err:
            sys.stdout = original_stdout  # Restore original stdout in case of error
            error_traceback = traceback.format_exc()
            error_collector.append({"attempt": count,
                                    "code_snapshot": code[:800],  # truncate long code
                                    "error_message": str(err),
                                    "error_traceback": error_traceback
                                    })


            if count == try_cnt:
                print(f"Failed to execute and debug the code within {try_cnt} times.")
                return code, error_collector


            debug_prompt = get_debug_prompt(exception=err, code=code, task=task, handbook_str=handbook_str)
            print("=" * 50)
            print("AI IS DEBUGGING THE CODE...")
            print("=" * 50)

            formatted_debug_prompt = f"{constants.debug_role}\n\n{debug_prompt}"

            # Use the same successful streaming method as code generation
            print("DEBUGGING RESPONSE:", end="", flush=True)

            try:
                kwargs = {}
                # Only pass reasoning_effort for GPT-5 models
                if reasoning_effort and model_name in ['gpt-5', 'gpt-5.1']:
                    kwargs['reasoning_effort'] = reasoning_effort

                debug_response_str =  unified_llm_call(
                    request_id=request_id,
                    messages=[
                        {"role": "system", "content": formatted_debug_prompt},
                    ],
                    model_name=model_name,
                    stream=stream,
                    **kwargs
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
            print("CODE_READY_URLENCODED:" + urllib.parse.quote(code), flush=True)
            sys.stdout.flush()  # Force flush to ensure output reaches UI

    return code,error_collector




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



