# OpenAI API Proxy

OpenAI API Proxy is a transparent middleware service built using Python and FastAPI, designed to sit between clients and
the OpenAI API. The proxy supports all models and APIs of OpenAI, streams OpenAI's responses back to clients in
real-time, and logs request timestamps, response times, status codes, request contents and response contents to a
database for future querying and maintenance.

Note that this program was originally implemented in collaboration with GPT-4.

## Features

1. **Transparent Proxy**: Supports all OpenAI models and APIs. Request paths, models, and OPENAI_API_KEY are all
   obtained from the original requests.
2. **Streaming**: Streams OpenAI's responses back to clients in real-time.
3. **Logging**: Records request timestamps, response times, status codes, request contents, response contents (if
   successful), and institution IDs to a database.
5. **Error Handling**: Handles request failures.

## Possible Use Cases

1. **Enterprises and Institutions**: Establish a secure middleware layer between clients and the OpenAI API for internal
   monitoring and management of API usage.
2. **Data Analysis**: Collect and analyze log data to understand hotspots and trends in API requests, optimizing API
   usage and performance.
3. **Billing and Quota Management**: Track API requests per institution to implement usage-based billing and quota
   management.
4. **Auditing and Security**: Ensure API requests comply with enterprise and institutional security policies and assist
   in auditing and tracking.
5. **Performance Monitoring**: Monitor API response times and status codes in real-time to identify and resolve
   potential performance issues.
6. **API Version Control and Migration**: Facilitate smooth API version migration by handling version discrepancies at
   the proxy layer, reducing client migration costs.

## Usage

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the proxy server:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

3. Make requests to the proxy server, specifying the OpenAI API endpoint, model, and any other required parameters:

```bash
curl -X POST "http://localhost:8000/v1/completions" \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <your_openai_api_key>" \
-d '{"model": "text-davinci-003", "prompt": "Once upon a time...", "max_tokens": 100, "temperature": 0}'
```

Replace `<your_openai_api_key>` with your actual OpenAI API key.

In summary, OpenAI API Proxy is a flexible and powerful tool designed to help enterprises and institutions better manage
and monitor their access to the OpenAI API, improving security, control, and performance.

## License

This program is licensed under the MIT License. Please see the [LICENSE](LICENSE) file for details.