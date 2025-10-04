# app.py
import os
import json
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# -----------------------
# CONFIG
# -----------------------
SHEET_ID = "1dO7a3evLEu7ONM5NQ1L7IQBt60xXJmsvvo0SS6rWZic"
SERVICE_ACCOUNT_FILE = "service_account.json"

# -----------------------
# INITIALIZE SESSION STATE
# -----------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = None
if "cache" not in st.session_state:
    st.session_state.cache = {}
if "force_rerun" not in st.session_state:
    st.session_state.force_rerun = False


# -----------------------
# INITIALIZE SESSION STATE
# -----------------------
for key in ["logged_in", "user", "role", "cache"]:
    if key not in st.session_state:
        if key == "cache":
            st.session_state[key] = {}
        else:
            st.session_state[key] = None if key != "logged_in" else False

# -----------------------
# GOOGLE SHEETS AUTHENTICATION
# -----------------------
import json, os
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

def authenticate_gsheets(sheet_id: str):
    """Authenticate to Google Sheets using either:
       1. SERVICE_ACCOUNT_JSON environment variable (Render, Streamlit Cloud)
       2. service_account.json file (local)"""

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = None

    try:
        # --- Option A: Environment variable (Render safe)
        if os.getenv("SERVICE_ACCOUNT_JSON"):
            raw = os.getenv("SERVICE_ACCOUNT_JSON")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                st.error("❌ SERVICE_ACCOUNT_JSON is not valid JSON.")
                st.stop()

            # Fix escaped newlines
            if "private_key" in data and "\\n" in data["private_key"]:
                data["private_key"] = data["private_key"].replace("\\n", "\n")

            creds = Credentials.from_service_account_info(data, scopes=scopes)

        # --- Option B: Local file (for local testing)
        elif os.path.exists("service_account.json"):
            creds = Credentials.from_service_account_file("service_account.json", scopes=scopes)
        else:
            st.error("❌ No credentials found. Provide SERVICE_ACCOUNT_JSON (env var) or service_account.json file.")
            st.stop()

        # Authorize client
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        st.success("✅ Google Sheets authentication successful!")
        return spreadsheet

    except gspread.SpreadsheetNotFound:
        st.error(
            "❌ Spreadsheet not found. Ensure SHEET_ID is correct and "
            "the service account email has **Editor** access."
        )
        st.stop()
    except Exception as e:
        st.error(
            f"❌ Failed to authenticate to Google Sheets.\n\n"
            "Possible causes:\n"
            "1️⃣ SERVICE_ACCOUNT_JSON not formatted correctly\n"
            "2️⃣ Missing line breaks in private_key (Render issue)\n"
            "3️⃣ Sheet not shared with service account\n"
            "4️⃣ Invalid SHEET_ID\n\n"
            f"Error: {e}"
        )
        st.stop()
# -----------------------
# OPEN SHEET
# -----------------------
spreadsheet = authenticate_gsheets(SHEET_ID)

# -----------------------
# SHEETS SETUP
# -----------------------
sheets_info = {
    "users": ["username","password","role","email","phone"],
    "students": ["username","name","department","email","phone","attendance_percentage",
                 "tution_fee_status","hostel_fee_status","exam_fee_status","transport_fee_status",
                 "books_issued","hostel_room"],
    "faculty": ["username","name","department","email","phone"],
    "requests": ["username","role","request_type","details","status","timestamp"],
    "payments": ["username","fee_type","amount","date","status"],
    "notifications": ["notification","date"],
    "recent_activity": ["username","role","action","timestamp"]
}

worksheet_objs = {}
for name, header in sheets_info.items():
    try:
        ws = spreadsheet.worksheet(name)
        existing_header = ws.row_values(1)
        if existing_header != header:
            if existing_header:
                ws.delete_rows(1)
            ws.insert_row(header, index=1)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=500, cols=20)
        ws.insert_row(header, index=1)
    worksheet_objs[name] = ws

def ws_by_name(name):
    return worksheet_objs[name]

# -----------------------
# UTILITIES
# -----------------------
def safe_get_all_records(ws, sheet_name):
    try:
        records = ws.get_all_records(expected_headers=sheets_info[sheet_name])
        return pd.DataFrame(records) if records else pd.DataFrame(columns=sheets_info[sheet_name])
    except gspread.exceptions.APIError:
        st.warning(f"Quota exceeded while reading {sheet_name}, returning empty dataframe.")
        return pd.DataFrame(columns=sheets_info[sheet_name])

def load_all_once():
    for name in sheets_info.keys():
        st.session_state.cache[name] = safe_get_all_records(ws_by_name(name), name)

# Helper functions
def append_row(sheet_name, row):
    ws_by_name(sheet_name).append_row(row)
    refresh_single(sheet_name)

def refresh_single(sheet_name):
    st.session_state.cache[sheet_name] = safe_get_all_records(ws_by_name(sheet_name), sheet_name)

def update_cell(sheet_name, row_idx, col_name, value):
    ws = ws_by_name(sheet_name)
    col_idx = sheets_info[sheet_name].index(col_name) + 1
    ws.update_cell(row_idx + 2, col_idx, value)  # +2 for header
    refresh_single(sheet_name)

def delete_user(username):
    ws = ws_by_name("users")
    users = st.session_state.cache["users"]
    idx = users[users["username"]==username].index
    if not idx.empty:
        ws.delete_rows(idx[0]+2)
        refresh_single("users")

def find_row_index_by_key(sheet_name, key_col, key_val):
    df = st.session_state.cache.get(sheet_name, pd.DataFrame())
    idx = df[df[key_col]==key_val].index
    return idx[0] if not idx.empty else None

def log_activity_local(user, role, action):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append_row("recent_activity", [user, role, action, ts])

# -----------------------
# DEMO USERS
# -----------------------
def ensure_demo_data():
    users_df = st.session_state.cache.get("users", pd.DataFrame())
    demo_users = [
        ["admin","pass123","Admin","admin@example.com","999000501"],
        ["student1","pass123","Student","student1@example.com","999000111"],
        ["student2","pass123","Student","student2@example.com","999000112"],
        ["librarian","pass123","Librarian","lib@example.com","999000301"],
        ["warden","pass123","Hostel Warden","warden@example.com","999000401"],
    ]
    existing = users_df["username"].str.lower().tolist() if not users_df.empty else []
    for u in demo_users:
        if u[0].lower() not in existing:
            ws_by_name("users").append_row(u)

load_all_once()
ensure_demo_data()

# -----------------------
# AUTHENTICATION FUNCTIONS
# -----------------------
def authenticate(username, password):
    users = st.session_state.cache.get("users")
    if users is None or users.empty:
        load_all_once()
        users = st.session_state.cache.get("users")
    uname = username.strip().lower()
    pwd = password.strip()
    users["username_norm"] = users["username"].str.strip().str.lower()
    users["password"] = users["password"].str.strip()
    matched = users[(users["username_norm"]==uname)&(users["password"]==pwd)]
    if not matched.empty:
        row = matched.iloc[0]
        return row["role"], row["username"]
    return None, None

def reset_login():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

# -----------------------
# STREAMLIT UI
# -----------------------
st.set_page_config(page_title="EcoOne ERP", layout="wide")
st.title("EcoOne ERP Prototype")

# Sidebar reset
if st.sidebar.button("Reset Login / Logout"):
    reset_login()

menu = ["Login","Sign Up"]
choice = st.sidebar.selectbox("Menu", menu)

# -----------------------
# SIGN UP
# -----------------------
if choice == "Sign Up":
    st.subheader("Create Account")
    su_username = st.text_input("Username", key="su_username")
    su_password = st.text_input("Password", type="password", key="su_password")
    su_role = st.selectbox("Role", ["Student","Faculty","Librarian","Hostel Warden","Admin"], key="su_role")
    su_email = st.text_input("Email", key="su_email")
    su_phone = st.text_input("Phone", key="su_phone")
    if st.button("Create Account", key="create_account"):
        users = st.session_state.cache.get("users", pd.DataFrame(columns=sheets_info["users"]))
        existing = users["username"].str.lower().tolist() if not users.empty else []
        if su_username.strip().lower() in existing:
            st.error("Username already exists.")
        else:
            append_row("users",[su_username.strip(), su_password.strip(), su_role, su_email.strip(), su_phone.strip()])
            st.success("Account created successfully! You can now login.")

# -----------------------
# LOGIN
# -----------------------
elif choice == "Login":
    st.subheader("Login")
    li_username = st.text_input("Username", key="login_username")
    li_password = st.text_input("Password", type="password", key="login_password")
    if st.button("Login", key="login_btn"):
        role, canon_user = authenticate(li_username, li_password)
        if role:
            st.session_state.logged_in = True
            st.session_state.user = canon_user
            st.session_state.role = role
            st.success(f"Logged in as {canon_user} ({role})")
            load_all_once()  # refresh cache to show dashboard
        else:
            st.error("Invalid username or password.")

# -----------------------
# POST-LOGIN DASHBOARD
# -----------------------
if st.session_state.logged_in:
    user = st.session_state.user
    role = st.session_state.role
    st.sidebar.markdown(f"**Logged in as:** {user} ({role})")
    if st.sidebar.button("Logout"):
        reset_login()

    
    st.subheader(f"Welcome, {user}!")
    if role=="Admin":
        st.subheader("Admin Dashboard")
        tabs = st.tabs(["Overview","Manage Users","Recent Activity"])
        

        with tabs[0]:
             st.subheader("Overview")

             # --- Users
             users_df = st.session_state.cache.get("users", pd.DataFrame())
             total_students = users_df[
                 users_df["role"].astype(str).str.strip().str.lower() == "student"
             ].shape[0] if not users_df.empty else 0
         
             # --- Payments
             payments_df = st.session_state.cache.get("payments", pd.DataFrame())
             students_df = st.session_state.cache.get("students", pd.DataFrame())

             if payments_df is None or payments_df.empty:
                 pending_payments_df = pd.DataFrame(columns=["username","fee_type","amount","date","status"])
             else:
                 # Normalize the status column
                 payments_df["status_norm"] = payments_df["status"].astype(str).str.strip().str.lower()
                 pending_payments_df = payments_df[payments_df["status_norm"] == "pending"]

             pending_count = len(pending_payments_df)

             st.metric("Total Students", total_students)
             st.metric("Total Payments", len(payments_df) if payments_df is not None else 0)
             st.metric("Pending Payments", pending_count)

             # --- Students with pending payments
             if not pending_payments_df.empty:
                 if students_df is not None and not students_df.empty:
                     # Merge to get student details
                     merged = pd.merge(
                         pending_payments_df,
                         students_df[["username","name","department"]],
                         on="username",
                         how="left"
                     )
                     display_df = merged[["name","department","fee_type","amount","date","status"]].fillna("")
                     st.markdown("### Students with Pending Payments")
                     st.dataframe(display_df)
                 else:
                     st.info("Student details not available.")
             else:
                st.info("No pending payments.")



        with tabs[1]:
            st.markdown("### Users")
            users_df = st.session_state.cache.get("users",pd.DataFrame())
            st.dataframe(users_df.fillna(""))

            st.markdown("#### Add User")
            uu = st.text_input("Username",key="admin_user_add")
            upw = st.text_input("Password",type="password",key="admin_user_pass")
            urole = st.selectbox("Role",["Student","Faculty","Librarian","Hostel Warden","Admin"],key="admin_user_role")
            if st.button("Add User",key="admin_user_add_btn"):
                append_row("users",[uu,upw,urole,"",""])
                refresh_single("users")
                st.session_state.force_rerun = not st.session_state.force_rerun
                st.success("User added.")

            st.markdown("#### Delete User")
            del_user = st.selectbox("Select User to Delete", users_df["username"].tolist() if not users_df.empty else [], key="del_user")
            if st.button("Delete User",key="del_user_btn"):
                delete_user(del_user)

        with tabs[2]:
            st.markdown("### Recent Activity")
            recent_df = st.session_state.cache.get("recent_activity",pd.DataFrame())
            st.dataframe(recent_df.fillna(""))

    # -----------------------
    # Student Dashboard
    # -----------------------
    elif role=="Student":
        st.subheader("Student Dashboard")
        students = st.session_state.cache.get("students",pd.DataFrame())
        idx = find_row_index_by_key("students","username",user)
        if idx is not None:
            row = students.loc[idx]
            st.write("**Personal Info**")
            st.write(row[["name","department","email","phone"]])
            st.write("**Fees Status**")
            st.write(row[["tution_fee_status","hostel_fee_status","exam_fee_status","transport_fee_status"]])
            st.write("**Books Issued:**",row.get("books_issued",""))
            st.write("**Hostel Room:**",row.get("hostel_room",""))

            st.subheader("Submit Requests")
            req_type = st.selectbox("Request Type", ["Library", "Hostel"], key="stu_req_type")
            details = st.text_input("Details", key="stu_req_details")
            if st.button("Submit Request", key="submit_req_btn"):
                if details.strip():
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    append_row("requests",[user, role, req_type, details.strip(), "Pending", ts])
                    st.success(f"{req_type} request submitted successfully.")
                    log_activity_local(user, role, f"Submitted {req_type} request: {details.strip()}")
                    refresh_single("requests")
                else:
                    st.error("Please enter request details.")

    # -----------------------
    # Librarian Dashboard
    # -----------------------
    elif role=="Librarian":
        st.subheader("Librarian Dashboard")
        reqs = st.session_state.cache.get("requests",pd.DataFrame())
        pending_lib = reqs[(reqs["request_type"]=="Library")&(reqs["status"]=="Pending")]
        st.markdown("### Pending Library Requests")
        if not pending_lib.empty:
            for i,r in pending_lib.iterrows():
                st.write(f"{r['username']} | {r['details']}")
                c1,c2 = st.columns(2)
                with c1:
                    if st.button(f"Approve_{i}",key=f"lib_app_{i}"):
                        update_cell("requests",i,"status","Approved")
                        sidx = find_row_index_by_key("students","username",r["username"])
                        if sidx is not None:
                            cur = st.session_state.cache["students"].at[sidx,"books_issued"]
                            new_val = (str(cur)+","+str(r["details"])).strip(",") if cur else r["details"]
                            update_cell("students",sidx,"books_issued",new_val)
                        log_activity_local(user,role,f"Approved library request {r['username']}")
                        st.session_state.force_rerun = not st.session_state.force_rerun
                with c2:
                    if st.button(f"Reject_{i}",key=f"lib_rej_{i}"):
                        update_cell("requests",i,"status","Rejected")
                        log_activity_local(user,role,f"Rejected library request {r['username']}")
                        st.session_state.force_rerun = not st.session_state.force_rerun
        else:
            st.info("No pending library requests")
        st.markdown("### Assigned Books Overview")
        students = st.session_state.cache.get("students", pd.DataFrame())
        assigned_books = students[students["books_issued"].notna() & (students["books_issued"]!="")]
        if not assigned_books.empty:
            st.dataframe(assigned_books[["name","department","books_issued"]])
        else:
            st.info("No books assigned yet.")
 

    # -----------------------
    # Hostel Warden Dashboard
    # -----------------------
    elif role=="Hostel Warden":
        st.subheader("Hostel Warden Dashboard")
        reqs = st.session_state.cache.get("requests",pd.DataFrame())
        pending_hostel = reqs[(reqs["request_type"]=="Hostel")&(reqs["status"]=="Pending")]
        st.markdown("### Pending Hostel Requests")
        if not pending_hostel.empty:
            for i,r in pending_hostel.iterrows():
                st.write(f"{r['username']} | {r['details']}")
                c1,c2 = st.columns(2)
                with c1:
                    if st.button(f"ApproveH_{i}",key=f"host_app_{i}"):
                        update_cell("requests",i,"status","Approved")
                        sidx = find_row_index_by_key("students","username",r["username"])
                        assigned = r["details"] if any(ch.isdigit() for ch in r["details"]) else "Assigned-"+datetime.now().strftime("%Y%m%d%H%M%S")
                        if sidx is not None:
                            update_cell("students",sidx,"hostel_room",assigned)
                        log_activity_local(user,role,f"Approved hostel request {r['username']}")
                        st.session_state.force_rerun = not st.session_state.force_rerun
                with c2:
                    if st.button(f"RejectH_{i}",key=f"host_rej_{i}"):
                        update_cell("requests",i,"status","Rejected")
                        log_activity_local(user,role,f"Rejected hostel request {r['username']}")
                        st.session_state.force_rerun = not st.session_state.force_rerun
        else:
            st.info("No pending hostel requests")
        
        st.markdown("### Assigned Hostel Rooms Overview")
        students = st.session_state.cache.get("students", pd.DataFrame())
        assigned_rooms = students[students["hostel_room"].notna() & (students["hostel_room"]!="")]
        if not assigned_rooms.empty:
            st.dataframe(assigned_rooms[["name","department","hostel_room"]])
        else:
            st.info("No hostel rooms assigned yet.")

