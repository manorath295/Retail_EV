"""
Enhanced Streamlit UI with Manual Product Browsing
Complete working version with all features
"""

import streamlit as st
import requests
import json
from datetime import datetime
from typing import Optional, List, Dict
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from config.supabase_config import get_storage
    SUPABASE_AVAILABLE = True
except:
    SUPABASE_AVAILABLE = False
    print("⚠️ Supabase not available, using memory storage")

# Page configuration
st.set_page_config(
    page_title="Retail AI Sales Agent",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API endpoint
API_URL = "http://localhost:8000"

# Custom CSS
st.markdown("""
<style>
    .product-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 20px;
        padding: 20px 0;
    }
    .product-card {
        border: 1px solid #ddd;
        border-radius: 12px;
        padding: 15px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .product-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .stock-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: 600;
        margin: 4px 0;
    }
    .stock-high { background: #d4edda; color: #155724; }
    .stock-medium { background: #fff3cd; color: #856404; }
    .stock-low { background: #f8d7da; color: #721c24; }
    .coupon-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'cart_total' not in st.session_state:
    st.session_state.cart_total = 0.0
if 'all_products' not in st.session_state:
    st.session_state.all_products = []
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = "chat"  # or "browse"


def load_all_products():
    """Load all products from API"""
    try:
        response = requests.get(f"{API_URL}/products", params={"limit": 100})
        if response.status_code == 200:
            data = response.json()
            st.session_state.all_products = data['products']
            return data['products']
    except Exception as e:
        st.error(f"Failed to load products: {e}")
    return []


def create_session():
    """Create a new chat session"""
    try:
        customer_id = "streamlit_user"
        
        response = requests.post(
            f"{API_URL}/chat",
            json={
                "message": "Hello",
                "session_id": "new",
                "customer_id": customer_id,
                "channel": "web"
            }
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.session_id = data['session_id']
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": data['response'],
                    "timestamp": datetime.now().isoformat(),
                    "suggestions": data.get('suggestions', []),
                }
            ]
            st.session_state.cart = []
            st.session_state.cart_total = 0.0
            
            # Load products
            load_all_products()
            
            return True
    except Exception as e:
        st.error(f"Failed to create session: {e}")
    return False


def send_message(message: str):
    """Send message to chatbot"""
    if not st.session_state.session_id:
        create_session()
    
    try:
        response = requests.post(
            f"{API_URL}/chat",
            json={
                "message": message,
                "session_id": st.session_state.session_id,
                "customer_id": "streamlit_user",
                "channel": "web"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Add user message
            st.session_state.messages.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.now().isoformat()
            })
            
            # Add assistant message
            st.session_state.messages.append({
                "role": "assistant",
                "content": data['response'],
                "timestamp": datetime.now().isoformat(),
                "suggestions": data.get('suggestions', []),
                "products": data.get('products'),
                "coupons": data.get('available_coupons', [])
            })
            
            # Update cart if changed
            if data.get('cart_update'):
                st.session_state.cart = data['cart_update']['items']
                st.session_state.cart_total = data['cart_update']['total']
            
            return True
        else:
            st.error(f"Error: {response.status_code}")
    
    except Exception as e:
        st.error(f"Failed to send message: {e}")
        import traceback
        st.error(traceback.format_exc())
    
    return False


def display_product_card_compact(product: Dict, col_index: int = 0):
    """Display a compact product card for grid view"""
    st.markdown(f"### {product.get('name', 'Product')}")
    
    # Image placeholder
    st.markdown(f"🖼️ *Image*")
    
    # Price and rating
    price = product.get('price', 0)
    rating = product.get('rating', 0)
    reviews = product.get('reviews_count', 0)
    
    st.markdown(f"**₹{price:,.0f}**")
    st.markdown(f"⭐ {rating}/5 ({reviews} reviews)")
    
    # SKU
    sku = product.get('sku', 'N/A')
    st.caption(f"SKU: {sku}")
    
    # Add to cart button with unique key
    import hashlib
    # Create unique key using SKU, name, and index to avoid duplicates
    unique_identifier = f"{sku}_{product.get('name', '')}_{col_index}"
    button_key = hashlib.md5(unique_identifier.encode()).hexdigest()[:12]
    
    if st.button(f"🛒 Add to Cart", key=f"add_{button_key}"):
        send_message(f"Add {product.get('name')} to cart")
        st.rerun()


# ========== SIDEBAR ==========
with st.sidebar:
    st.title("🛍️ Retail AI Agent")
    
    st.markdown("---")
    
    # View Mode Selector
    st.subheader("📍 Navigation")
    view_mode = st.radio(
        "Select View:",
        ["💬 AI Chat", "📦 Browse Products", "🛒 Cart & Checkout"],
        key="view_selector"
    )
    
    if view_mode == "💬 AI Chat":
        st.session_state.view_mode = "chat"
    elif view_mode == "📦 Browse Products":
        st.session_state.view_mode = "browse"
    else:
        st.session_state.view_mode = "cart"
    
    st.markdown("---")
    
    # Session info
    if st.session_state.session_id:
        st.success(f"🟢 Connected")
        st.caption(f"Session: {st.session_state.session_id[:12]}...")
        
        if st.button("🔄 New Session"):
            create_session()
            st.rerun()
    else:
        st.warning("⚪ Not connected")
        if st.button("🔌 Connect"):
            create_session()
            st.rerun()
    
    st.markdown("---")
    
    # Cart summary
    st.subheader("🛒 Shopping Cart")
    if st.session_state.cart:
        st.metric("Items", len(st.session_state.cart))
        st.metric("Total", f"₹{st.session_state.cart_total:,.2f}")
        
        for item in st.session_state.cart:
            st.markdown(f"**{item['name']}** x{item['quantity']}")
            st.caption(f"₹{item['price'] * item['quantity']:,.2f}")
        
        if st.button("💳 Checkout"):
            st.session_state.view_mode = "cart"
            send_message("I want to checkout, tell me if any coupon available for me")
            st.rerun()
    else:
        st.info("Cart is empty")
    
    st.markdown("---")
    
    # Quick actions
    st.subheader("⚡ Quick Actions")
    
    if st.button("👟 Browse Footwear"):
        send_message("Show me footwear")
        st.session_state.view_mode = "chat"
        st.rerun()
    
    if st.button("📱 Browse Electronics"):
        send_message("Show me electronics")
        st.session_state.view_mode = "chat"
        st.rerun()
    
    if st.button("📦 Check Stock"):
        send_message("Tell me what's in stock")
        st.session_state.view_mode = "chat"
        st.rerun()


# ========== MAIN AREA ==========

if st.session_state.view_mode == "chat":
    # ========== CHAT VIEW ==========
    st.title("💬 Chat with AI Sales Agent")
    
    # Display messages
    messages_container = st.container()
    
    with messages_container:
        if not st.session_state.messages:
            st.info("👋 Welcome! Start chatting to browse products and shop with our AI assistant.")
        
        for msg in st.session_state.messages:
            if msg['role'] == 'user':
                with st.chat_message("user"):
                    st.markdown(msg['content'])
            else:
                with st.chat_message("assistant"):
                    st.markdown(msg['content'])
                    
                    # Show products if available
                    if msg.get('products'):
                        st.markdown("---")
                        st.markdown("**📦 Recommended Products:**")
                        
                        cols = st.columns(3)
                        for idx, product in enumerate(msg['products'][:6]):
                            with cols[idx % 3]:
                                display_product_card_compact(product, idx)
                    
                    # Show coupons if available
                    if msg.get('coupons'):
                        st.markdown("---")
                        st.markdown("**🎁 Available Coupons:**")
                        for coupon in msg['coupons'][:3]:
                            discount = f"{coupon['discount_value']}%" if coupon['discount_type'] == 'percentage' else f"₹{coupon['discount_value']}"
                            st.markdown(f"""
                            <div class="coupon-card">
                                <h4>🎟️ {coupon['code']}</h4>
                                <p>{coupon['description']}</p>
                                <p><strong>Save: {discount}</strong></p>
                                {f"<p>Min purchase: ₹{coupon.get('min_purchase', 0):.0f}</p>" if coupon.get('min_purchase') else ""}
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # Show suggestions
                    if msg.get('suggestions'):
                        st.markdown("---")
                        cols = st.columns(len(msg['suggestions'][:4]))
                        for i, suggestion in enumerate(msg['suggestions'][:4]):
                            with cols[i]:
                                if st.button(suggestion, key=f"sug_{msg['timestamp']}_{i}"):
                                    send_message(suggestion)
                                    st.rerun()
    
    # Chat input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        if send_message(user_input):
            st.rerun()

elif st.session_state.view_mode == "browse":
    # ========== MANUAL PRODUCT BROWSING ==========
    st.title("📦 Browse All Products")
    
    # Load products if not loaded
    if not st.session_state.all_products:
        load_all_products()
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        category_filter = st.selectbox(
            "Category",
            ["All", "Footwear", "Clothing", "Electronics", "Accessories"]
        )
    
    with col2:
        min_price = st.number_input("Min Price", min_value=0, value=0, step=500)
    
    with col3:
        max_price = st.number_input("Max Price", min_value=0, value=50000, step=1000)
    
    # Apply filters
    filtered_products = st.session_state.all_products
    
    if category_filter != "All":
        filtered_products = [p for p in filtered_products if p.get('category') == category_filter]
    
    if min_price > 0:
        filtered_products = [p for p in filtered_products if p.get('price', 0) >= min_price]
    
    if max_price > 0:
        filtered_products = [p for p in filtered_products if p.get('price', 0) <= max_price]
    
    st.markdown(f"### Found {len(filtered_products)} products")
    
    # Display products in grid
    if filtered_products:
        cols_per_row = 3
        for i in range(0, len(filtered_products), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(filtered_products):
                    with col:
                        product = filtered_products[i + j]
                        with st.container():
                            display_product_card_compact(product, i + j)
    else:
        st.info("No products found. Try adjusting filters.")

else:
    # ========== CART & CHECKOUT VIEW ==========
    st.title("🛒 Shopping Cart & Checkout")
    
    if st.session_state.cart:
        # Cart items
        st.subheader("Your Items")
        
        total = 0
        for item in st.session_state.cart:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            with col1:
                st.markdown(f"**{item['name']}**")
                st.caption(f"SKU: {item['sku']}")
            
            with col2:
                st.markdown(f"₹{item['price']:,.0f}")
            
            with col3:
                st.markdown(f"x {item['quantity']}")
            
            with col4:
                subtotal = item['price'] * item['quantity']
                st.markdown(f"₹{subtotal:,.0f}")
                total += subtotal
        
        st.markdown("---")
        st.markdown(f"### Total: ₹{total:,.2f}")
        
        # Checkout button
        if st.button("💳 Proceed to Checkout", type="primary"):
            send_message("I want to checkout, tell me if any coupon available for me")
            st.session_state.view_mode = "chat"
            st.rerun()
        
        # Show latest checkout message if available
        if st.session_state.messages:
            last_msg = st.session_state.messages[-1]
            if last_msg.get('role') == 'assistant' and last_msg.get('coupons'):
                st.markdown("---")
                st.subheader("🎁 Available Coupons")
                for coupon in last_msg['coupons']:
                    discount = f"{coupon['discount_value']}%" if coupon['discount_type'] == 'percentage' else f"₹{coupon['discount_value']}"
                    st.markdown(f"""
                    <div class="coupon-card">
                        <h4>🎟️ {coupon['code']}</h4>
                        <p>{coupon['description']}</p>
                        <p><strong>Save: {discount}</strong></p>
                        {f"<p>Min purchase: ₹{coupon.get('min_purchase', 0):.0f}</p>" if coupon.get('min_purchase') else ""}
                    </div>
                    """, unsafe_allow_html=True)
    
    else:
        st.info("Your cart is empty")
        if st.button("🛍️ Start Shopping"):
            st.session_state.view_mode = "browse"
            st.rerun()


# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "Retail AI Sales Agent v3.0 | Complete with Manual Browsing & Checkout"
    "</div>",
    unsafe_allow_html=True
)

# Initialize on first load
if not st.session_state.session_id:
    create_session()
