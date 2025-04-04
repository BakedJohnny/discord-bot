from ast import parse
import discord
import requests
import base64
import re
from discord import app_commands
from discord.ext import commands, tasks
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import asyncio
import time
from typing import Optional, List
from datetime import datetime
import gspread_formatting as gf
from gspread.utils import rowcol_to_a1
from poolfinder import get_data_based_on_selection, get_data_by_talent_type


SPREADSHEET_ID = 'sheetid'
# Google Sheets and Drive setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
client = gspread.authorize(creds)
drive_service = build('drive', 'v3', credentials=creds)

# Fetch the column titles from the first row of the sheet
trade_sheet = client.open("Trade Records").sheet1
trade_column_titles = trade_sheet.row_values(1)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable Message Content Intent
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')
    await bot.tree.sync()  # Sync commands globally

# Function to create an embed for multiple rows of data
def create_embed(rows_data, column_titles, start_row_num, current_page, total_pages, search_terms):
    embed = discord.Embed(title=f"Details", color=discord.Color.blue())

    # Formatting each row
    table = ""
    for row_num, row_data in enumerate(rows_data, start=start_row_num):
        row_content = " | ".join(f"{title}: {bold_search_terms(data, search_terms) or 'N/A'}" for title, data in zip(column_titles, row_data))
        table += f"Row {row_num}\n{row_content}\n\n"

    # Adding the table to the embed
    embed.add_field(name="Records", value=table, inline=False)
    embed.set_footer(text=f"Page {current_page + 1}/{total_pages + 1}")
    return embed

# Function to create an embed for a single row of data
def create_detailed_embed(row_data, column_titles, row_num, current_page, total_pages):
    embed = discord.Embed(title=f"Details for Row {row_num}", color=discord.Color.green())

    # Formatting the row
    for title, data in zip(column_titles, row_data):
        embed.add_field(name=title, value=data or 'N/A', inline=True)

    embed.set_footer(text=f"Page {current_page + 1}/{total_pages + 1}")
    return embed

# Function to bold search terms in the text
def bold_search_terms(text, search_terms):
    if text is None:
        return text
    for term in search_terms:
        text = text.replace(term, f"**{term}**")
    return text

# Function to create a paginator for talent types
class TalentTypePaginator(discord.ui.View):
    def __init__(self, data: List[str], exact_talent_type: str, color=discord.Color.green()):
        super().__init__(timeout=None)
        self.data = data
        self.title = f"Talent Type Finder Results for '{exact_talent_type}'"
        self.color = color
        self.current_page = 0
        self.embeds = self.create_embeds()

    def create_embeds(self):
        embeds = []
        embed = discord.Embed(title=self.title, color=self.color)
        
        for index, item in enumerate(self.data):
            if index > 0 and index % 10 == 0:
                embed.set_footer(text=f"Page {len(embeds) + 1} of {len(self.data) // 10 + 1}\nUse /poolfind to know more about specific talents.")
                embeds.append(embed)
                embed = discord.Embed(title=self.title, color=self.color)
            embed.add_field(name="Talent Name", value=item, inline=False)
        
        embed.set_footer(text=f"Page {len(embeds) + 1} of {len(self.data) // 10 + 1}\nUse /poolfind to know more about specific talents.")
        embeds.append(embed)
        return embeds

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def send_initial_message(self, interaction: discord.Interaction):
        await interaction.followup.send(embed=self.embeds[self.current_page], view=self)

class Paginator(discord.ui.View):
    def __init__(self, data, column_titles, rows_per_embed, search_terms, user_id, allowed_user_id=None, timeout=180):
        super().__init__(timeout=timeout)
        self.data = data
        self.column_titles = column_titles
        self.rows_per_embed = rows_per_embed
        self.search_terms = search_terms
        self.user_id = user_id
        self.allowed_user_id = allowed_user_id
        self.current_page = 0
        self.rows_per_page_index = 0  # Index to track the current rows per page option
        self.detailed_view = False  # Flag to toggle between views

    @property
    def total_pages(self):
        if self.detailed_view:
            return len(self.data) - 1
        else:
            return (len(self.data) + self.rows_per_embed - 1) // self.rows_per_embed - 1

    def check(self, interaction: discord.Interaction):
        return interaction.user.id == self.user_id or (self.allowed_user_id and interaction.user.id == self.allowed_user_id)

    @property
    def embed(self):
        if self.detailed_view:
            row_num = self.current_page + 1
            row_data = self.data[self.current_page]
            return create_detailed_embed(row_data, self.column_titles, row_num, self.current_page, self.total_pages)
        else:
            start = self.current_page * self.rows_per_embed
            end = start + self.rows_per_embed
            rows_data = self.data[start:end]
            return create_embed(rows_data, self.column_titles, start + 1, self.current_page, self.total_pages, self.search_terms)

    @discord.ui.button(label='Jump to Start', style=discord.ButtonStyle.secondary)
    async def jump_to_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.check(interaction):
            self.current_page = 0
            await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.check(interaction):
            if self.detailed_view:
                if self.current_page > 0:
                    self.current_page -= 1
            else:
                if self.current_page > 0:
                    self.current_page -= 1
            await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.check(interaction):
            if self.detailed_view:
                if self.current_page < len(self.data) - 1:
                    self.current_page += 1
            else:
                if self.current_page < self.total_pages:
                    self.current_page += 1
            await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label='Jump to Last', style=discord.ButtonStyle.secondary)
    async def jump_to_last(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.check(interaction):
            self.current_page = self.total_pages
            await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label='Toggle View', style=discord.ButtonStyle.secondary)
    async def toggle_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.check(interaction):
            self.detailed_view = not self.detailed_view
            self.current_page = 0  # Reset to the first page
            await interaction.response.edit_message(embed=self.embed, view=self)

class RevertPermissionView(discord.ui.View):
    def __init__(self, file_id, user_id, allowed_user_id=None, timeout=180):
        super().__init__(timeout=timeout)
        self.file_id = file_id
        self.user_id = user_id
        self.allowed_user_id = allowed_user_id

    def check(self, interaction: discord.Interaction):
        return interaction.user.id == self.user_id or (self.allowed_user_id and interaction.user.id == self.allowed_user_id)

    @discord.ui.button(label='Revert Permissions', style=discord.ButtonStyle.danger)
    async def revert_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.check(interaction):
            remove_share_link(self.file_id)
            await interaction.response.send_message("The share link has been removed and the sheet is now restricted.", ephemeral=True)

@bot.tree.command(name="fetch_trade", description="Fetch trade details by row number")
@app_commands.describe(row="Row number to fetch")
async def fetch_trade(interaction: discord.Interaction, row: int):
    try:
        # Fetch the row data from Google Sheets
        row_data = trade_sheet.row_values(row)
        if row_data:
            embed = create_embed([row_data], trade_column_titles, row, 0, 0, [])
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"No data found in row {row}.")
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_all_trades", description="Fetch all trade details")
@app_commands.describe(allowed_user="Optional user who can also interact with the buttons")
async def fetch_all_trades(interaction: discord.Interaction, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        if all_data:
            paginator = Paginator(all_data, trade_column_titles, rows_per_embed=5, search_terms=[], user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send("No data found.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_trade_by_user", description="Fetch trade details by user IDs")
@app_commands.describe(user_ids="Comma-separated list of user IDs to fetch trades for", allowed_user="Optional user who can also interact with the buttons")
async def fetch_trade_by_user(interaction: discord.Interaction, user_ids: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        user_id_variations = [uid.strip().lower() for uid in user_ids.split(',')]
        user_data = [row for row in all_data[1:] if any(uid in str(row[trade_column_titles.index("user id")]).lower() for uid in user_id_variations)]
        if user_data:
            paginator = Paginator(user_data, trade_column_titles, rows_per_embed=5, search_terms=user_id_variations, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send(f"No trades found for user IDs {user_ids}.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_trade_by_category", description="Fetch trade details by categories")
@app_commands.describe(categories="Comma-separated list of categories to fetch trades for", allowed_user="Optional user who can also interact with the buttons")
async def fetch_trade_by_category(interaction: discord.Interaction, categories: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        category_variations = [cat.strip().lower() for cat in categories.split(',')]
        category_data = [row for row in all_data[1:] if any(cat in str(row[trade_column_titles.index("category")]).lower() for cat in category_variations)]
        if category_data:
            paginator = Paginator(category_data, trade_column_titles, rows_per_embed=5, search_terms=category_variations, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send(f"No trades found for categories {categories}.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_trade_by_date", description="Fetch trade details by dates")
@app_commands.describe(dates="Comma-separated list of dates to fetch trades for (YYYY-MM-DD)", allowed_user="Optional user who can also interact with the buttons")
async def fetch_trade_by_date(interaction: discord.Interaction, dates: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        date_variations = [date.strip() for date in dates.split(',')]
        date_data = [row for row in all_data[1:] if any(date in str(row[trade_column_titles.index("date")]).lower() for date in date_variations)]
        if date_data:
            paginator = Paginator(date_data, trade_column_titles, rows_per_embed=5, search_terms=date_variations, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send(f"No trades found for dates {dates}.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_trade_by_item", description="Fetch trade details by items")
@app_commands.describe(items="Comma-separated list of items to fetch trades for", allowed_user="Optional user who can also interact with the buttons")
async def fetch_trade_by_item(interaction: discord.Interaction, items: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        item_column_index = trade_column_titles.index("items(s)")
        item_variations = [item.strip().lower() for item in items.split(',')]
        item_data = [row for row in all_data[1:] if any(item in str(row[item_column_index]).lower() for item in item_variations)]
        if item_data:
            paginator = Paginator(item_data, trade_column_titles, rows_per_embed=5, search_terms=item_variations, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send(f"No trades found for items {items}.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_trade_by_buyer", description="Fetch trade details by buyers")
@app_commands.describe(buyers="Comma-separated list of buyers to fetch trades for", allowed_user="Optional user who can also interact with the buttons")
async def fetch_trade_by_buyer(interaction: discord.Interaction, buyers: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        buyer_variations = [buyer.strip().lower() for buyer in buyers.split(',')]
        buyer_data = [row for row in all_data[1:] if any(buyer in str(row[trade_column_titles.index("buyer")]).lower() for buyer in buyer_variations)]
        if buyer_data:
            paginator = Paginator(buyer_data, trade_column_titles, rows_per_embed=5, search_terms=buyer_variations, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send(f"No trades found for buyers {buyers}.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="fetch_trade_by_price", description="Fetch trade details by price")
@app_commands.describe(price="Comma-separated list of prices to fetch trades for", allowed_user="Optional user who can also interact with the buttons")
async def fetch_trade_by_price(interaction: discord.Interaction, price: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.defer()  # Defer the response to allow more time for processing
        # Fetch all data from Google Sheets
        all_data = trade_sheet.get_all_values()
        price_variations = [p.strip().lower() for p in price.split(',')]
        price_data = [row for row in all_data[1:] if any(p in str(row[trade_column_titles.index("price")]).lower() for p in price_variations)]
        if price_data:
            paginator = Paginator(price_data, trade_column_titles, rows_per_embed=5, search_terms=price_variations, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.followup.send(embed=paginator.embed, view=paginator)
        else:
            await interaction.followup.send(f"No trades found for prices {price}.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

# New command to add a record
@bot.tree.command(name="add_record", description="Add a new record to the trade sheet")
@app_commands.describe(
    buyer="Buyer involved in the trade",
    user_id="ID of the user",
    message_id="ID of the message",
    item="Item(s) involved in the trade",
    price="Price of the trade",
    category="Category of the trade",
    date="Date of the trade (dd/mm/yyyy)"
)
async def add_record(
    interaction: discord.Interaction,
    buyer: Optional[str] = None,
    user_id: Optional[str] = None,
    message_id: Optional[str] = None,
    item: Optional[str] = None,
    price: Optional[str] = None,
    category: Optional[str] = None,
    date: Optional[str] = None
):
    try:
        # Parse the date in dd/mm/yyyy format or use current date if empty
        if date:
            try:
                parsed_date = datetime.strptime(date, "%d/%m/%Y")
                formatted_date = parsed_date.strftime("%d %B %Y")  # Format the date as dd mmmm yyyy
                print(f"Parsed date: {formatted_date}")  # Debug print
            except ValueError:
                await interaction.response.send_message("Invalid date format. Please use dd/mm/yyyy.")
                return
        else:
            parsed_date = datetime.now()
            formatted_date = parsed_date.strftime("%d %B %Y")  # Format the date as dd mmmm yyyy
            print(f"Using current date: {formatted_date}")  # Debug print
        # Prepare the new row data
        new_row_data = [
            buyer or "",
            user_id or "",
            message_id or "",
            item or "",
            price or "",
            category or "",
            formatted_date
        ]

        print(f"New row data: {new_row_data}")  # Debug print

        # Add the new row to the Google Sheet
        trade_sheet.append_row(new_row_data, value_input_option='USER_ENTERED')
        # Get the number of the last row (the row we just added)
        last_row = len(trade_sheet.get_all_values())
        print(f"Last row number: {last_row}")  # Debug print

        # Set the format of the date column to 'DATE'
        date_column_index = trade_column_titles.index("date") + 1
        print(f"Date column index: {date_column_index}")  # Debug print
        cell_range = f"{rowcol_to_a1(last_row, date_column_index)}:{rowcol_to_a1(last_row, date_column_index)}"
        gf.format_cell_range(trade_sheet, cell_range, gf.cellFormat(
            numberFormat=gf.numberFormat(type='DATE', pattern='dd mmmm yyyy')
        ))

        await interaction.response.send_message("Record added successfully!")
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {str(e)}")

# Function to create a shareable link and change permissions with retry logic
def create_share_link(file_id):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Change permissions to make the file publicly accessible
            permission = {
                'type': 'anyone',
                'role': 'reader',
            }
            drive_service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()

            # Get the shareable link
            file = drive_service.files().get(fileId=file_id, fields='webViewLink').execute()
            return file.get('webViewLink')
        except HttpError as error:
            if error.resp.status in [500, 503]:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f'An error occurred: {error}')
                return None
    return None

# Function to remove the shareable link and revert permissions
def remove_share_link(file_id):
    try:
        # List the permissions
        permissions = drive_service.permissions().list(fileId=file_id).execute()
        for permission in permissions.get('permissions', []):
            if permission['type'] == 'anyone':
                # Remove the 'anyone' permission
                drive_service.permissions().delete(
                    fileId=file_id,
                    permissionId=permission['id']
                ).execute()
    except HttpError as error:
        print(f'An error occurred: {error}')

# Function to get the file ID by name
def get_file_id_by_name(file_name):
    try:
        print(f"Searching for file with name: {file_name}")
        response = drive_service.files().list(
            q=f"name='{file_name}'",
            spaces='drive',
            fields='files(id, name)',
        ).execute()
        files = response.get('files', [])
        print(f"Found files: {files}")  # Debug log
        if not files:
            return None
        return files[0]['id']
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

@bot.tree.command(name="sheet_link", description="Share a Google Sheet and create a shareable link")
@app_commands.describe(sheet_name="The name of the Google Sheet to share", allowed_user="Optional user who can also interact with the button")
async def sheet_link(interaction: discord.Interaction, sheet_name: str, allowed_user: discord.Member = None):
    try:
        await interaction.response.send_message("Processing your request, please wait...")

        file_id = get_file_id_by_name(sheet_name)
        if not file_id:
            await interaction.edit_original_response(content=f"No sheet found with the name {sheet_name}.")
            return

        share_link = create_share_link(file_id)
        if share_link:
            view = RevertPermissionView(file_id, user_id=interaction.user.id, allowed_user_id=allowed_user.id if allowed_user else None)
            await interaction.edit_original_response(content=f"Sheet shared successfully! [View Sheet]({share_link})", view=view)
        else:
            await interaction.edit_original_response(content="Failed to create a shareable link.")
    except discord.errors.NotFound:
        print("Failed to send follow-up message: interaction expired.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

def create_poolfind_embed(data, inputs):
    embed = discord.Embed(title="Pool Finder Results", color=discord.Color.blue())
    embed.description = f"Results for values: `{', '.join(inputs)}` in column B"

    for index, row in enumerate(data):
        # Ensure there's enough columns in the row
        if len(row) >= 5:
            col_a = row[0]
            col_b = row[1]
            col_c = row[2]
            col_d = row[3]
            hyperlink = row[4]

            # Format col_b as a clickable link if it contains a URL
            if hyperlink and hyperlink.lower() != 'false':
                col_b = f"[{col_b}]({hyperlink})"

            # Add blue upward and downward arrow indicators
            if index == 0:
                indicator = "🔵⬆️ Top"
            elif index == len(data) - 1:
                indicator = "🔵⬇️ Bottom"
            else:
                indicator = ""

            embed.add_field(name=f"Row Details {indicator}", value=f"**Priority:** {col_a}\n**Talent Name:** {col_b}\n**Rarity:** {col_c}\n**Additional Info:** {col_d}", inline=False)

    return embed

@bot.tree.command(name="poolfind", description="Find data in the pool finder sheet")
@app_commands.describe(required_input="Required value for column B", optional_input_1="Optional value 1 for column B", optional_input_2="Optional value 2 for column B", optional_input_3="Optional value 3 for column B", optional_input_4="Optional value 4 for column B")
async def poolfind(interaction: discord.Interaction, required_input: str, optional_input_1: Optional[str] = None, optional_input_2: Optional[str] = None, optional_input_3: Optional[str] = None, optional_input_4: Optional[str] = None):
    try:
        await interaction.response.defer()  # Defer the interaction response to allow more time for processing

        # Collect the inputs
        inputs = [required_input]
        if optional_input_1: inputs.append(optional_input_1)
        if optional_input_2: inputs.append(optional_input_2)
        if optional_input_3: inputs.append(optional_input_3)
        if optional_input_4: inputs.append(optional_input_4)

        data = get_data_based_on_selection(SPREADSHEET_ID, inputs, creds)
        if data:
            embed = create_poolfind_embed(data, inputs)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("No data found for the given selections.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="talenttype", description="Find talents by talent type in the pool finder sheet")
@app_commands.describe(talent_type="Talent type to search for in column C")
async def talenttype(interaction: discord.Interaction, talent_type: str):
    try:
        await interaction.response.defer()  # Defer the interaction response to allow more time for processing

        data, exact_talent_type = get_data_by_talent_type(SPREADSHEET_ID, talent_type, creds)
        if data:
            paginator = TalentTypePaginator(data, exact_talent_type=exact_talent_type)
            await paginator.send_initial_message(interaction)
        else:
            await interaction.followup.send("No data found for the given talent type.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")


bot.run('TOKEN')
