from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
import re

def initialize_sheets_api(creds):
    service = build('sheets', 'v4', credentials=creds)
    return service.spreadsheets()

def fetch_data(spreadsheet_id, sheet_name, range_name, creds):
    full_range = f"'{sheet_name}'!{range_name}"
    sheets = initialize_sheets_api(creds)
    result = sheets.get(spreadsheetId=spreadsheet_id, ranges=full_range, fields="sheets.data.rowData.values(effectiveValue, formattedValue, userEnteredValue)").execute()
    values = []
    for row in result.get('sheets', [])[0].get('data', [])[0].get('rowData', []):
        row_values = []
        for cell in row.get('values', []):
            if 'userEnteredValue' in cell and 'formulaValue' in cell['userEnteredValue']:
                formula = cell['userEnteredValue']['formulaValue']
                match = re.match(r'=HYPERLINK\("(.*?)","(.*?)"\)', formula)
                if match:
                    row_values.append(match.group(1))  # Append the link
                    row_values.append(match.group(2))  # Append the display text
                else:
                    row_values.append(cell.get('formattedValue', 'N/A'))
            else:
                row_values.append(cell.get('formattedValue', 'N/A'))
        values.append(row_values)
    return values

def get_data_based_on_selection(sheet_id, x_value, y_value, creds):
    # Hardcoded sheet name
    sheet_name = "Talents Between Filter"
    # Accessing the specified sheet within the spreadsheet
    range_name = "A2:C"  # Adjust this range as per your sheet structure
    data = fetch_data(sheet_id, sheet_name, range_name, creds)
    
    # Debugging: Print fetched data
    print("Fetched Data:", data)

    # Process the data to include rows where column B matches either x_value or y_value
    filtered_data = []
    for row in data:
        if len(row) >= 4 and (row[2] == x_value or row[2] == y_value):
            filtered_data.append([row[0], row[3], row[4], row[1]])
    
    # Debugging: Print filtered data
    print("Filtered Data:", filtered_data)
    
    return filtered_data