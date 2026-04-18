import streamlit as st

# 1. SET THE MASTER CONFIG ONCE
st.set_page_config(page_title="Miloto Fleet System", layout="wide", page_icon="🚛")

# 2. DEFINE THE PAGES
oil_page = st.Page("views/oil_and_servicing.py", title="Oil & Servicing", icon="🛢️")
logistics_page = st.Page("views/logistics.py", title="Logistics Trips", icon="🚛")
workshop_page = st.Page("views/workshop.py", title="Workshop Log", icon="🛠️")

# 3. INITIALIZE SECURITY STATE
if "role" not in st.session_state:
    st.session_state.role = None

# 4. MOBILE-OPTIMIZED CSS STYLING
st.markdown("""
    <style>
    /* 1. Maximize screen real estate on mobile */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    
    /* 2. Hide default Streamlit branding and headers for a native feel */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* 3. Make the sidebar navigation links much larger and tap-friendly */
    [data-testid="stSidebarNavItems"] a {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        padding-top: 15px !important;
        padding-bottom: 15px !important;
    }
    
    /* 4. Ensure dataframes fit nicely without breaking the screen width */
    [data-testid="stDataFrame"] {
        width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# 5. THE LOGIN SCREEN
if st.session_state.role is None:
    # Center the login box
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.title("🔐 Miloto Fleet Login")
        st.write("Please enter your access PIN to continue.")
        
        pin = st.text_input("PIN Code", type="password")
        if st.button("Secure Login", use_container_width=True):
            if pin == "1111":  # Master Admin
                st.session_state.role = "Admin"
                st.rerun()
            elif pin == "2222":  # Logistics Team
                st.session_state.role = "Logistics"
                st.rerun()
            elif pin == "3333":  # Mechanics
                st.session_state.role = "Mechanic"
                st.rerun()
            elif pin == "4444":  # Workshop Checkers
                st.session_state.role = "Checker"
                st.rerun()
            else:
                st.error("❌ Invalid PIN. Please try again.")

# 6. ROUTE THE USER BASED ON THEIR ROLE
else:
    # Show Logout Button in Sidebar
    st.sidebar.button("Logout 👋", on_click=lambda: st.session_state.update({"role": None}))
    
    # Assign pages based on who logged in
    if st.session_state.role == "Admin":
        pg = st.navigation([oil_page, logistics_page, workshop_page])
    elif st.session_state.role == "Logistics":
        pg = st.navigation([logistics_page])
    elif st.session_state.role == "Mechanic":
        pg = st.navigation([oil_page, workshop_page])
    elif st.session_state.role == "Checker":
        pg = st.navigation([workshop_page])
    
    # Run the selected page
    pg.run()