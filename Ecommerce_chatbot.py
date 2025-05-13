
import streamlit as st
import pymysql
import ollama
import re
from decimal import Decimal

# ---------------------------
# Database Configuration & Connection
# ---------------------------
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "VK18.123",
    "db": "products_db",
    "port": 3306
}

def get_db_connection():
    return pymysql.connect(
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        db=db_config["db"],
        port=db_config["port"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

# ---------------------------
# Fetch Products from Database
# ---------------------------
def fetch_products(search_keyword):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql_query = """
                SELECT id, product_name, selling_price, mrp_price, discount_percent, product_link,
                       category, category_url, image_url, manufacturer_name, sku_master_id,
                       cleaned_description
                FROM Products
                WHERE (%s IS NULL OR MATCH(product_name, cleaned_description)
                       AGAINST(%s IN NATURAL LANGUAGE MODE));
            """
            cursor.execute(sql_query, (search_keyword, search_keyword))
            return cursor.fetchall()
    finally:
        conn.close()

# ---------------------------
# Cart Management in MySQL
# ---------------------------
def add_to_cart(user_id, product_id, product_name, quantity=1):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT quantity FROM Cart WHERE user_id = %s AND product_id = %s", (user_id, product_id))
            result = cursor.fetchone()

            if result:
                new_quantity = result["quantity"] + quantity
                cursor.execute(
                    "UPDATE Cart SET quantity = %s WHERE user_id = %s AND product_id = %s",
                    (new_quantity, user_id, product_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO Cart (user_id, product_id, product_name, quantity) VALUES (%s, %s, %s, %s)",
                    (user_id, product_id, product_name, quantity)
                )

            conn.commit()
            return f"✅ **{product_name}** (x{quantity}) added to cart!"
    finally:
        conn.close()

def remove_from_cart(user_id, product_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Cart WHERE user_id = %s AND product_id = %s", (user_id, product_id))
            conn.commit()
            return "✅ Product removed from cart."
    finally:
        conn.close()

def clear_cart(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM Cart WHERE user_id = %s", (user_id,))
            conn.commit()
            return "🗑️ Cart cleared successfully."
    finally:
        conn.close()

def fetch_cart(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT C.product_id, C.product_name, P.selling_price, P.image_url, C.quantity
                FROM Cart C
                JOIN Products P ON C.product_id = P.id
                WHERE C.user_id = %s
            """, (user_id,))
            return cursor.fetchall()
    finally:
        conn.close()

# ---------------------------
# LLaMA Chatbot Logic (Updated)
# ---------------------------
def generate_llama_response(user_query, user_id):
    # Check if user wants to add a specific quantity of a product to cart
    match = re.search(r"add (\d+) (.*?) to cart", user_query.lower())
    if match:
        quantity = int(match.group(1))
        product_name = match.group(2).strip()

        products = fetch_products(product_name)  # Fetch products matching the provided name
        for product in products:
            if product_name in product["product_name"].lower():  # Check for match in product name
                message = add_to_cart(user_id, product["id"], product["product_name"], quantity)
                return message, []  # Directly return the success message

    # If no direct match, continue with regular product search
    products = fetch_products(user_query)
    if not products:
        return "No matching products found.", []

    formatted_text = "Here are some products based on your search:\n\n"
    for product in products[:5]:
        formatted_text += f"🛍 **{product['product_name']}**\n💰 Price: ₹{product['selling_price']}\n🔗 [View]({product['product_link']})\n\n"

    # Pass to LLaMA only if no direct cart operation was detected
    prompt = f"""
    You are an intelligent shopping assistant. A user searched for "{user_query}". 
    Based on the database, here are the relevant products:
    {formatted_text}
    Generate a response and determine if the user wants to add something to the cart.
    """

    response = ollama.chat(model="llama3.1:8b", messages=[{"role": "user", "content": prompt}])
    return response['message']['content'], products



# ---------------------------
# Streamlit UI
# ---------------------------
st.set_page_config(page_title="🛒 E-Commerce Chatbot", layout="wide")
st.title("🛒 E-Commerce Chatbot")

user_id = 1
search_query = st.text_input("Search for a product:", "")

if search_query:
    response, products = generate_llama_response(search_query, user_id)
    st.markdown(response)
    for product in products:
        with st.expander(f"🛍 {product['product_name']} (₹{product['selling_price']})"):
            st.image(product['image_url'], width=150)
            st.write(f"🔗 [View Product]({product['product_link']})")
            if st.button(f"🛒 Add to Cart - {product['product_name']}", key=product["id"]):
                message = add_to_cart(user_id, product["id"], product["product_name"], 1)
                st.success(message)

# ---------------------------
# Sidebar: Cart UI
# ---------------------------
with st.sidebar:
    st.title("🛍 Your Cart")
    cart_items = fetch_cart(user_id)

    if cart_items:
        total_price = 0
        for item in cart_items:
            col1, col2, col3 = st.columns([4, 2, 2])
            with col1:
                st.markdown(f"**{item['product_name']}** - ₹{item['selling_price']} x {item['quantity']}")
            with col2:
                st.image(item['image_url'], width=50)
            with col3:
                if st.button("❌ Remove", key=item['product_id']):
                    st.warning(remove_from_cart(user_id, item['product_id']))
            total_price += float(item['selling_price']) * item['quantity']
        
        st.markdown(f"**Total: ₹{total_price:.2f}**")
        if st.button("🛒 Proceed to Checkout"):
            st.success("✅ Checkout process initiated!")
        if st.button("🗑️ Clear Cart"):
            st.warning(clear_cart(user_id))
    else:
        st.info("Your cart is empty. Start adding products!")
