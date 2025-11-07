"""
Telegram Bot Integration
Enables customers to interact with the AI agent via Telegram.
"""

import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config.settings import settings
from agents.sales_agent import get_sales_agent
from agents.state import create_initial_state
from config.supabase_config import save_conversation, load_conversation


class TelegramBotHandler:
    """Handles Telegram bot interactions."""
    
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.enabled = self.token is not None and self.token != ""
        
        if self.enabled:
            self.application = Application.builder().token(self.token).build()
            self._setup_handlers()
            print("✅ Telegram bot initialized")
        else:
            self.application = None
            print("⚠️  Telegram bot disabled (no token)")
        
        self.sales_agent = get_sales_agent()
    
    def _setup_handlers(self):
        """Setup Telegram command and message handlers."""
        
        # Commands
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("cart", self.cart_command))
        self.application.add_handler(CommandHandler("offers", self.offers_command))
        
        # Messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Callback queries (button clicks)
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        
        welcome_text = """
🛍️ Welcome to Retail AI Shopping Assistant!

I can help you:
• Browse and search products
• Check availability and prices
• Add items to cart
• Complete purchases
• Track orders
• Handle returns & exchanges

Just send me a message to get started!

Quick commands:
/help - Show all commands
/cart - View your cart
/offers - See current offers
        """
        
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        
        help_text = """
📚 Available Commands:

/start - Start the bot
/help - Show this help message
/cart - View your shopping cart
/offers - See current offers and discounts

You can also just chat with me naturally! Try:
• "Show me running shoes"
• "What's on sale?"
• "Track my order"
• "I need to return an item"
        """
        
        await update.message.reply_text(help_text)
    
    async def cart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cart command."""
        
        user_id = update.effective_user.id
        session_id = f"telegram_{user_id}"
        
        # Load conversation state
        state = load_conversation(session_id)
        
        if state and state.get("cart"):
            cart = state["cart"]
            cart_total = state.get("cart_total", 0)
            
            cart_text = f"🛒 Your Cart:\n\n"
            for item in cart:
                cart_text += f"• {item['name']} x{item['quantity']} - ₹{item['price'] * item['quantity']:,.2f}\n"
            
            cart_text += f"\n**Total: ₹{cart_total:,.2f}**"
            
            # Add checkout button
            keyboard = [[InlineKeyboardButton("Proceed to Checkout", callback_data="checkout")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(cart_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text("Your cart is empty! Start shopping by sending me a message.")
    
    async def offers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /offers command."""
        
        from agents.loyalty_agent import get_loyalty_agent
        
        loyalty_agent = get_loyalty_agent()
        promotions = loyalty_agent.promotions
        
        if promotions:
            offers_text = "🎁 Current Offers:\n\n"
            for promo in promotions[:5]:
                offers_text += f"• **{promo['promo_code']}**: {promo['description']}\n"
            
            await update.message.reply_text(offers_text, parse_mode='Markdown')
        else:
            await update.message.reply_text("No active offers right now. Check back soon!")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages."""
        
        user_id = update.effective_user.id
        user_message = update.message.text
        session_id = f"telegram_{user_id}"
        
        # Load or create conversation state
        state = load_conversation(session_id)
        
        if state is None:
            state = create_initial_state(
                session_id=session_id,
                channel="telegram"
            )
        
        # Process message
        try:
            result = await self.sales_agent.process_message(
                message=user_message,
                state=state,
                session_id=session_id,
                channel="telegram"
            )
            
            # Save conversation
            save_conversation(session_id, result["state"])
            
            # Send response
            response_text = result["response"]
            
            # Create inline keyboard with suggestions
            keyboard = []
            if result.get("suggestions"):
                for suggestion in result["suggestions"][:3]:
                    keyboard.append([InlineKeyboardButton(suggestion, callback_data=f"msg:{suggestion}")])
            
            if keyboard:
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(response_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response_text)
            
            # Send product cards if available
            if result.get("products"):
                await self.send_product_cards(update, result["products"][:3])
        
        except Exception as e:
            print(f"Error processing Telegram message: {e}")
            await update.message.reply_text("Sorry, I encountered an error. Please try again.")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks."""
        
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        
        if callback_data.startswith("msg:"):
            # User clicked a suggestion button
            message_text = callback_data[4:]
            
            # Simulate user message
            update.message = query.message
            update.message.text = message_text
            
            await self.handle_message(update, context)
        
        elif callback_data == "checkout":
            user_id = update.effective_user.id
            session_id = f"telegram_{user_id}"
            
            # Process checkout
            state = load_conversation(session_id)
            
            if state:
                result = await self.sales_agent.process_message(
                    message="I want to checkout",
                    state=state,
                    session_id=session_id,
                    channel="telegram"
                )
                
                save_conversation(session_id, result["state"])
                await query.message.reply_text(result["response"])
    
    async def send_product_cards(self, update: Update, products: list):
        """Send product cards to user."""
        
        for product in products:
            product_text = f"""
**{product['name']}**

₹{product['price']:,.2f}
⭐ {product['rating']}/5 ({product['reviews_count']} reviews)

{product.get('recommendation_reason', '')}
            """
            
            keyboard = [[InlineKeyboardButton("Add to Cart", callback_data=f"add:{product['sku']}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send product image if available
            if product.get('image_url'):
                try:
                    await update.message.reply_photo(
                        photo=product['image_url'],
                        caption=product_text.strip(),
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except:
                    await update.message.reply_text(
                        product_text.strip(),
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(
                    product_text.strip(),
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
    
    def run(self):
        """Start the Telegram bot."""
        
        if not self.enabled:
            print("Telegram bot is not enabled")
            return
        
        print("🤖 Starting Telegram bot...")
        self.application.run_polling()
    
    async def send_notification(self, user_id: int, message: str):
        """Send a notification to a user."""
        
        if not self.enabled:
            return False
        
        try:
            await self.application.bot.send_message(chat_id=user_id, text=message)
            return True
        except Exception as e:
            print(f"Error sending Telegram notification: {e}")
            return False


# Global handler instance
telegram_handler = TelegramBotHandler()


def run_telegram_bot():
    """Run the Telegram bot (blocking)."""
    telegram_handler.run()


if __name__ == "__main__":
    print("""
    ============================================
    🤖 Telegram Bot Setup Instructions
    ============================================
    
    1. Create a Telegram Bot:
       - Open Telegram and search for @BotFather
       - Send /newbot command
       - Follow instructions to create your bot
       - Copy the bot token
    
    2. Configure your .env file:
       TELEGRAM_BOT_TOKEN=your_bot_token_here
    
    3. Run the bot:
       python -m channels.telegram_handler
       
       Or integrate with your main app:
       from channels.telegram_handler import run_telegram_bot
       run_telegram_bot()
    
    4. Test:
       - Search for your bot on Telegram
       - Send /start to begin
       - Start chatting!
    
    ============================================
    
    Commands your bot will support:
    /start - Welcome message
    /help - Show help
    /cart - View shopping cart
    /offers - See current offers
    """)
    
    if telegram_handler.enabled:
        run_telegram_bot()
    else:
        print("\n⚠️  Please configure TELEGRAM_BOT_TOKEN in your .env file")
