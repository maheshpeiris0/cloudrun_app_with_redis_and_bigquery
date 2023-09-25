from flask import Flask, render_template, jsonify, request
import os
import json  # <--- Use the built-in json module
from google.cloud import bigquery
from google.cloud import secretmanager
from google.oauth2 import service_account
import uuid
import redis

# Google Cloud Project ID
project_id = 'project-id'
secret_name = 'my-service-key' # Secret name
client_sm = secretmanager.SecretManagerServiceClient()

# Access the secret
name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
response = client_sm.access_secret_version(request={"name": name})

# Extract the secret value (JSON string)
secret_value_json = response.payload.data.decode("UTF-8")

# Load the JSON string into a dictionary
secret_value_dict = json.loads(secret_value_json)

# Use the dictionary to create credentials
credentials = service_account.Credentials.from_service_account_info(
    secret_value_dict
)



redis_host = os.environ.get("REDISHOST", "localhost")
redis_port = int(os.environ.get("REDISPORT", 6379))
redis_client = redis.StrictRedis(host=redis_host, port=redis_port)


# Initialize a BigQuery client with the credentials
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# Initialize the Flask application

app = Flask(__name__)



@app.route('/')
def index():
    # Fetch data from Redis
    all_keys = redis_client.keys('*')
    
    data_from_redis = []
    for key in all_keys:
        redis_val = redis_client.get(key)
        if redis_val:
            try:
                json_val = json.loads(redis_val.decode())
                data_from_redis.append(json_val)
            except json.JSONDecodeError:
                print(f"Error decoding JSON for key {key}: {redis_val.decode()}")

    # Transform Redis data to match the expected format for the template (without ID)
    data = []
    for item in data_from_redis:
        if 'name' in item and 'age' in item and 'country' in item:
            data.append({'name': item['name'], 'age': item['age'], 'country': item['country']})

    # Render template with data
    return render_template('index.html', data=data)



# Define a route for page_two
@app.route('/page_two')
def page_two():
    return render_template('page_two.html')

# Define a route for page_three
@app.route('/eventform')
def event_form():
    return render_template('eventform.html')


# upload data Google BigQuery
@app.route('/submit_form', methods=['POST'])
def submit_form():
    try:
        data = request.json
        name = data['name']
        age = data['age']
        country = data['country']
        ID = str(uuid.uuid4())

        # Write data to BigQuery
        dataset_name = 'test_table' # BigQuery dataset name
        table_name = 'travel_app' # BigQuery table name
        table_ref = client.dataset(dataset_name).table(table_name)
        table = client.get_table(table_ref)

        # Append data
        rows_to_insert = [(name, age, country, ID)]
        errors = client.insert_rows(table, rows_to_insert)

        # The key will be the UUID, and the value will be a JSON string representation of the user's details.
        redis_client.set(ID, json.dumps({"name": name, "age": age, "country": country}))

        if errors:
            raise RuntimeError("Error while inserting rows to BigQuery:", errors)

        return jsonify({"message": "Form data submitted successfully!"}), 200
    except Exception as e:
        print(e)  # Log the error for debugging
        return jsonify({"message": "An error occurred while submitting the form."}), 500



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)