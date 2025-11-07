"""
Generate sample data for Retail AI Agent.
Creates customers, products, inventory, purchase history, and promotions.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from faker import Faker

fake = Faker('en_IN')  # Indian locale
DATA_DIR = Path(__file__).parent

# Seed for reproducibility
random.seed(42)
fake.seed_instance(42)


def generate_customers(count=15):
    """Generate sample customers with profiles."""
    
    customers = []
    loyalty_tiers = ['Bronze', 'Silver', 'Gold', 'Platinum']
    
    for i in range(count):
        loyalty_points = random.randint(0, 20000)
        
        # Determine tier based on points
        if loyalty_points >= 15000:
            tier = 'Platinum'
        elif loyalty_points >= 5000:
            tier = 'Gold'
        elif loyalty_points >= 1000:
            tier = 'Silver'
        else:
            tier = 'Bronze'
        
        customer = {
            'customer_id': f'CUST{1000 + i}',
            'name': fake.name(),
            'email': fake.email(),
            'phone': fake.phone_number(),
            'created_at': (datetime.now() - timedelta(days=random.randint(30, 730))).isoformat(),
            'loyalty_tier': tier,
            'loyalty_points': loyalty_points,
            'total_orders': random.randint(1, 50),
            'total_spent': random.randint(5000, 200000),
            'favorite_categories': random.sample(['Footwear', 'Clothing', 'Electronics', 'Accessories'], k=2),
            'address': {
                'street': fake.street_address(),
                'city': random.choice(['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai']),
                'state': random.choice(['MH', 'DL', 'KA', 'TS', 'TN']),
                'pincode': fake.postcode()
            }
        }
        
        customers.append(customer)
    
    # Save to file
    with open(DATA_DIR / 'customers.json', 'w') as f:
        json.dump(customers, f, indent=2)
    
    print(f"✅ Generated {len(customers)} customers")
    return customers


def generate_products(count=100):
    """Generate product catalog."""
    
    products = []
    
    categories = {
        'Footwear': {
            'brands': ['Nike', 'Adidas', 'Puma', 'Reebok', 'New Balance', 'Woodland', 'Bata'],
            'types': ['Running Shoes', 'Casual Shoes', 'Sneakers', 'Formal Shoes', 'Sports Shoes', 'Sandals'],
            'price_range': (999, 15999)
        },
        'Clothing': {
            'brands': ['Zara', 'H&M', 'Levi\'s', 'Allen Solly', 'Van Heusen', 'Peter England', 'Wrangler'],
            'types': ['T-Shirt', 'Shirt', 'Jeans', 'Trousers', 'Jacket', 'Sweatshirt', 'Hoodie'],
            'price_range': (499, 7999)
        },
        'Electronics': {
            'brands': ['Apple', 'Samsung', 'OnePlus', 'Xiaomi', 'Sony', 'JBL', 'boAt'],
            'types': ['Smartphone', 'Smartwatch', 'Earbuds', 'Headphones', 'Speaker', 'Power Bank'],
            'price_range': (999, 99999)
        },
        'Accessories': {
            'brands': ['Fossil', 'Tommy Hilfiger', 'Ray-Ban', 'Titan', 'Fastrack', 'Skagen'],
            'types': ['Watch', 'Wallet', 'Belt', 'Sunglasses', 'Bag', 'Cap', 'Tie'],
            'price_range': (299, 19999)
        }
    }
    
    sku_counter = 1000
    
    for category, data in categories.items():
        # Number of products per category
        num_products = count // len(categories)
        
        for i in range(num_products):
            brand = random.choice(data['brands'])
            product_type = random.choice(data['types'])
            
            # Generate SKU
            sku = f"{category[:3].upper()}{sku_counter}"
            sku_counter += 1
            
            # Price
            min_price, max_price = data['price_range']
            base_price = random.randint(min_price, max_price)
            
            # Add discount for some products
            discount_pct = random.choice([0, 0, 0, 5, 10, 15, 20, 25])
            price = base_price * (1 - discount_pct / 100)
            
            # Rating and reviews
            rating = round(random.uniform(3.5, 5.0), 1)
            reviews_count = random.randint(10, 500)
            
            # Tags
            tags = []
            if discount_pct > 0:
                tags.append('On Sale')
            if rating >= 4.5:
                tags.append('Best Seller')
            if reviews_count > 300:
                tags.append('Popular')
            if random.random() < 0.2:
                tags.append('New Arrival')
            
            product = {
                'sku': sku,
                'name': f'{brand} {product_type}',
                'category': category,
                'brand': brand,
                'description': f'Premium quality {product_type.lower()} from {brand}. Perfect for everyday use.',
                'price': round(price, 2),
                'original_price': base_price if discount_pct > 0 else None,
                'discount_percentage': discount_pct if discount_pct > 0 else None,
                'rating': rating,
                'reviews_count': reviews_count,
                'is_featured': random.random() < 0.3,
                'is_available': True,
                'tags': tags,
                'specifications': {
                    'warranty': f'{random.choice([6, 12, 24])} months',
                    'return_policy': '30 days return'
                },
                'image_url': f'https://via.placeholder.com/300x300.png?text={brand}+{product_type}',
                'created_at': (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat()
            }
            
            products.append(product)
    
    # Save to file
    with open(DATA_DIR / 'products.json', 'w') as f:
        json.dump(products, f, indent=2)
    
    print(f"✅ Generated {len(products)} products")
    return products


def generate_inventory(products):
    """Generate inventory across warehouses and stores."""
    
    inventory = []
    
    locations = [
        {'id': 'WH_CENTRAL', 'type': 'warehouse', 'name': 'Central Warehouse'},
        {'id': 'MUM01', 'type': 'store', 'name': 'Mumbai Central'},
        {'id': 'DEL01', 'type': 'store', 'name': 'Delhi CP'},
        {'id': 'BLR01', 'type': 'store', 'name': 'Bangalore Koramangala'},
        {'id': 'HYD01', 'type': 'store', 'name': 'Hyderabad Banjara'},
        {'id': 'CHN01', 'type': 'store', 'name': 'Chennai T.Nagar'}
    ]
    
    for product in products:
        # Warehouse always has stock
        warehouse_qty = random.randint(50, 500)
        inventory.append({
            'sku': product['sku'],
            'location_id': 'WH_CENTRAL',
            'location_type': 'warehouse',
            'quantity': warehouse_qty,
            'reserved': random.randint(0, min(10, warehouse_qty)),
            'last_updated': datetime.now().isoformat()
        })
        
        # Stores have variable stock
        for store in locations[1:]:  # Skip warehouse
            if random.random() < 0.7:  # 70% chance store has this product
                store_qty = random.randint(5, 50)
                inventory.append({
                    'sku': product['sku'],
                    'location_id': store['id'],
                    'location_type': 'store',
                    'quantity': store_qty,
                    'reserved': random.randint(0, min(3, store_qty)),
                    'last_updated': datetime.now().isoformat()
                })
    
    # Save to file
    with open(DATA_DIR / 'inventory.json', 'w') as f:
        json.dump(inventory, f, indent=2)
    
    print(f"✅ Generated {len(inventory)} inventory records")
    return inventory


def generate_purchase_history(customers, products):
    """Generate purchase history for customers."""
    
    history = []
    
    for customer in customers:
        num_purchases = customer['total_orders']
        
        for i in range(num_purchases):
            # Select random products
            num_items = random.randint(1, 4)
            purchased_products = random.sample(products, num_items)
            
            order_date = datetime.now() - timedelta(days=random.randint(1, 365))
            
            for product in purchased_products:
                history.append({
                    'customer_id': customer['customer_id'],
                    'order_id': f'ORD{random.randint(10000, 99999)}',
                    'sku': product['sku'],
                    'product_name': product['name'],
                    'category': product['category'],
                    'brand': product['brand'],
                    'quantity': random.randint(1, 3),
                    'price': product['price'],
                    'order_date': order_date.isoformat(),
                    'status': random.choice(['Delivered', 'Delivered', 'Delivered', 'In Transit', 'Processing'])
                })
    
    # Save to file
    with open(DATA_DIR / 'purchase_history.json', 'w') as f:
        json.dump(history, f, indent=2)
    
    print(f"✅ Generated {len(history)} purchase records")
    return history


def generate_promotions():
    """Generate active promotions and offers."""
    
    promotions = [
        {
            'promo_id': 'FLAT500',
            'code': 'FLAT500',
            'description': 'Flat ₹500 off on orders above ₹2000',
            'discount_type': 'fixed',
            'discount_value': 500,
            'min_purchase': 2000,
            'max_discount': 500,
            'valid_from': (datetime.now() - timedelta(days=10)).isoformat(),
            'valid_until': (datetime.now() + timedelta(days=20)).isoformat(),
            'usage_limit': 1000,
            'used_count': random.randint(100, 500),
            'applicable_categories': [],
            'is_active': True
        },
        {
            'promo_id': 'SAVE20',
            'code': 'SAVE20',
            'description': '20% off on Electronics',
            'discount_type': 'percentage',
            'discount_value': 20,
            'min_purchase': 0,
            'max_discount': 5000,
            'valid_from': (datetime.now() - timedelta(days=5)).isoformat(),
            'valid_until': (datetime.now() + timedelta(days=15)).isoformat(),
            'usage_limit': 500,
            'used_count': random.randint(50, 300),
            'applicable_categories': ['Electronics'],
            'is_active': True
        },
        {
            'promo_id': 'FOOT15',
            'code': 'FOOT15',
            'description': '15% off on Footwear',
            'discount_type': 'percentage',
            'discount_value': 15,
            'min_purchase': 0,
            'max_discount': 2000,
            'valid_from': (datetime.now() - timedelta(days=7)).isoformat(),
            'valid_until': (datetime.now() + timedelta(days=23)).isoformat(),
            'usage_limit': 750,
            'used_count': random.randint(100, 400),
            'applicable_categories': ['Footwear'],
            'is_active': True
        },
        {
            'promo_id': 'FIRST100',
            'code': 'FIRST100',
            'description': '₹100 off on first purchase',
            'discount_type': 'fixed',
            'discount_value': 100,
            'min_purchase': 500,
            'max_discount': 100,
            'valid_from': (datetime.now() - timedelta(days=30)).isoformat(),
            'valid_until': (datetime.now() + timedelta(days=60)).isoformat(),
            'usage_limit': 10000,
            'used_count': random.randint(1000, 3000),
            'applicable_categories': [],
            'is_active': True,
            'first_purchase_only': True
        }
    ]
    
    # Save to file
    with open(DATA_DIR / 'promotions.json', 'w') as f:
        json.dump(promotions, f, indent=2)
    
    print(f"✅ Generated {len(promotions)} promotions")
    return promotions


def main():
    """Generate all data."""
    
    print("🚀 Starting data generation...")
    print(f"📁 Data directory: {DATA_DIR}")
    
    # Create data directory if it doesn't exist
    DATA_DIR.mkdir(exist_ok=True)
    
    # Generate data
    customers = generate_customers(15)
    products = generate_products(100)
    inventory = generate_inventory(products)
    purchase_history = generate_purchase_history(customers, products)
    promotions = generate_promotions()
    
    print("\n✨ Data generation complete!")
    print(f"""
📊 Summary:
- Customers: {len(customers)}
- Products: {len(products)}
- Inventory Records: {len(inventory)}
- Purchase History: {len(purchase_history)}
- Promotions: {len(promotions)}
    """)
    
    print(f"\n📁 Files created in: {DATA_DIR}")
    print("- customers.json")
    print("- products.json")
    print("- inventory.json")
    print("- purchase_history.json")
    print("- promotions.json")


if __name__ == "__main__":
    main()
