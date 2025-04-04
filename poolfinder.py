from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
import re

def initialize_sheets_api(creds):
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

def fetch_data(spreadsheet_id, sheet_name, range_name, creds):
    full_range = f"'{sheet_name}'!{range_name}"
    sheets = initialize_sheets_api(creds)
    result = sheets.values().get(spreadsheetId=spreadsheet_id, range=full_range).execute()
    values = result.get('values', [])
    return values

def fetch_hyperlinks(spreadsheet_id, sheet_name, col_range, creds):
    full_range = f"'{sheet_name}'!{col_range}"
    sheets = initialize_sheets_api(creds)
    result = sheets.get(spreadsheetId=spreadsheet_id, ranges=full_range, fields="sheets.data.rowData.values.hyperlink,sheets.data.rowData.values.formattedValue").execute()
    hyperlinks = []
    for row in result.get('sheets', [])[0].get('data', [])[0].get('rowData', []):
        cell = row.get('values', [{}])[0]
        hyperlink = cell.get('hyperlink')
        formatted_value = cell.get('formattedValue', 'N/A')
        hyperlinks.append((formatted_value, hyperlink))
    return hyperlinks

def fetch_data_and_hyperlinks(spreadsheet_id, sheet_name, data_range, hyperlink_range, creds):
    data = fetch_data(spreadsheet_id, sheet_name, data_range, creds)
    hyperlinks = fetch_hyperlinks(spreadsheet_id, sheet_name, hyperlink_range, creds)
    return data, hyperlinks

def normalize_input(value):
    # Normalize the input by making it lowercase and replacing spaces and hyphens with a common character
    return re.sub(r'[\s-]', '-', value.lower())

def get_data_based_on_selection(sheet_id, inputs, creds):
    # Updated sheet name and ranges
    sheet_name = "Pet Talents Priority List"
    data_range = "A:G"  # We need columns A to G
    
    # Fetch data
    data = fetch_data(sheet_id, sheet_name, data_range, creds)
    
    # Normalize the inputs
    normalized_inputs = [normalize_input(input) for input in inputs]
    
    # Process the data to include rows where column B matches any of the inputs
    filtered_data = []
    for row in data:
        if len(row) >= 7:
            normalized_row_b = normalize_input(row[1])
            if normalized_row_b in normalized_inputs:
                # Prepare additional info
                additional_info = row[3]
                if row[6].lower() == 'true':
                    additional_info += ", Retired"
                filtered_data.append([row[0], row[1], row[2], additional_info, row[4]])
    
    return filtered_data

def get_data_by_talent_type(sheet_id, talent_type, creds):
    # Updated sheet name and ranges
    sheet_name = "Pet Talents Priority List"
    data_range = "B4:C"  # We only need columns B and C
    
    # Fetch data
    data = fetch_data(sheet_id, sheet_name, data_range, creds)
    
    # Normalize the talent type input
    normalized_talent_type = normalize_input(talent_type)

    # Process the data to include rows where column C matches the talent type
    filtered_data = []
    exact_match_value = None
    for row in data:
        if len(row) >= 2:
            normalized_row_talent_type = normalize_input(row[1])
            if normalized_row_talent_type == normalized_talent_type:
                filtered_data.append(row[0])  # Only add data from column B
                if exact_match_value is None:
                    exact_match_value = row[1]  # Capture the exact matching value
    
    return filtered_data, exact_match_value