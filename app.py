import streamlit as st

# 1. SET THE MASTER CONFIG (Sleek abstract icon)
st.set_page_config(page_title="Miloto Fleet System", layout="wide", page_icon=":material/all_inclusive:")

# 2. DEFINE THE PAGES (Upgraded to Material Symbols)
oil_page = st.Page("oil_and_servicing.py", title="Oil Analysis", icon=":material/opacity:")
logistics_page = st.Page("logistics.py", title="Fleet Logistics", icon=":material/route:")
workshop_page = st.Page("workshop.py", title="Workshop Log", icon=":material/precision_manufacturing:")

# 3. INITIALIZE SECURITY STATE
if "role" not in st.session_state:
    st.session_state.role = None

# 4. PREMIUM UI/UX CSS STYLING
st.markdown("""
    <style>
    /* IMPORT PREMIUM GOOGLE FONTS */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Montserrat:wght@600;700;800&display=swap');

    /* APPLY GLOBAL FONTS */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }
    
    /* APPLY HEADER FONTS (Sleek, Geometric) */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px !important;
    }

    /* MAXIMIZE SCREEN REAL ESTATE (Mobile Optimized) */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    
    /* HIDE DEFAULT STREAMLIT BRANDING */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* SLEEK SIDEBAR NAVIGATION */
    [data-testid="stSidebarNavItems"] a {
        font-size: 1.15rem !important;
        font-weight: 500 !important;
        padding-top: 15px !important;
        padding-bottom: 15px !important;
        border-radius: 8px !important;
        transition: all 0.2s ease;
    }
    
    /* Ensure dataframes fit nicely without breaking the screen width */
    [data-testid="stDataFrame"] {
        width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# 5. THE LOGIN SCREEN (Sleek & Centered)
if st.session_state.role is None:
    st.title(":material/lock: Miloto Secure Access")
    st.markdown("<p style='font-size: 1.1rem; color: #666;'>Please authenticate to enter the operational dashboard.</p>", unsafe_allow_html=True)
    st.write("")
    
    pin = st.text_input("Access PIN", type="password")
    if st.button("Authenticate", use_container_width=True, type="primary"):
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
            st.error(":material/error: Invalid PIN. Please try again.")

# 6. ROUTE THE USER BASED ON THEIR ROLE
else:
    # Show Logout Button in Sidebar
    st.sidebar.button("Log Out :material/logout:", on_click=lambda: st.session_state.update({"role": None}))
    
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
