
# 🧠 AI-Powered Conversational Sales Agent for ABFRL (EY Techathon 6.0)

> **Reimagining retail sales with Agentic AI that unifies the customer experience across web, app, messaging, and in-store channels.**

---

## 🚀 Project Overview

Customers today experience **fragmented retail journeys** — switching between online browsing, mobile apps, WhatsApp chats, and physical stores without continuity.  
Our solution introduces an **Agentic AI Conversational Sales System** that emulates a **top-tier human associate** — delivering personalized, consistent, and persuasive conversations across all touchpoints.

The system integrates **Generative AI + Machine Learning + Modular Worker Agents** to handle:
- Product discovery  
- Inventory checks  
- Payments  
- Fulfillment  
- Loyalty management  
- Post-purchase support  

The result?  
💬 **Seamless omnichannel engagement**  
🛍️ **Higher Average Order Value (AOV)**  
⚡ **Improved conversion rates**

---

## 🎯 Problem Statement

> Customers face fragmented experiences when moving between online browsing, mobile app shopping, messaging apps, and in-store interactions.  
> Limited bandwidth among sales associates leads to missed up-sell and cross-sell opportunities.  
>  
> The goal is to increase **Average Order Value (AOV)** and **conversion rates** by offering a **unified, human-like conversational journey** that anticipates customer needs, provides tailored recommendations, and facilitates sales across all channels.

---

## 💡 Proposed Solution

We built an **Agentic AI architecture** where a central **Sales Agent** orchestrates specialized **Worker Agents**, ensuring context-aware interaction and real-time orchestration across services.

### 🧩 Key Components
- **Sales Agent:** Central brain managing conversation flow and task routing.  
- **Worker Agents:**
  - *Recommendation Agent* → Personalized product bundles & upsell logic  
  - *Inventory Agent* → Real-time availability across store & warehouse  
  - *Payment Agent* → Handles secure payments, retries & confirmations  
  - *Fulfillment Agent* → Delivery scheduling & in-store pickup  
  - *Loyalty Agent* → Applies reward points, offers, and coupons  
  - *Post-Purchase Agent* → Manages feedback, returns & engagement  

---

## ⚙️ System Architecture

### 🧠 **High-Level Architecture Diagram**
<img width="1933" height="1558" alt="image" src="https://github.com/user-attachments/assets/aa695fb8-1a7f-4d74-9a56-798a5e11e16f" />


## 🔁 Workflow: End-to-End User Journey

### **Flowchart**
<img width="531" height="580" alt="image" src="https://github.com/user-attachments/assets/71b86d7d-93b0-421c-95f8-8e51beee04a6" />


---

## 🧰 Tech Stack

| Category | Tools & Technologies |
|-----------|----------------------|
| **Frontend** | React.js, Tailwind CSS, ShadCN, React Native, Expo |
| **Backend** | FastAPI, Node.js, Express |
| **AI / GenAI** | OpenAI GPT, LangChain, LangGraph, Pinecone |
| **ML** | TensorFlow, Scikit-learn, Pandas |
| **Database** | MongoDB |
| **Messaging / Voice** | Twilio API (WhatsApp), Speech-to-Text (Whisper) |
| **Infra / DevOps** | Docker, PM2, Nginx, GitHub Actions (CI/CD) |
| **Visualization Tools** | Eraser.io (Architecture), Napkin.ai (Flowcharts) |

---

## 🧪 Data & Simulation

- **Synthetic Customer Profiles:** 10+ mock profiles with demographics, purchase history, and loyalty tiers.  
- **Mock APIs:**  
  - Product Catalog API (SKUs, categories, prices, images)  
  - Inventory API (real-time stock)  
  - Payment Gateway (authorization, declines)  
  - Loyalty Service (points, offers)  
  - POS Integration (in-store payments)  

---

## 🧭 Implementation Plan

| Phase | Task | Deliverable |
|--------|------|-------------|
| **Phase 1** | Agent Architecture Setup | Sales Agent + Worker Agent skeletons |
| **Phase 2** | Backend API Integration | Catalog, Inventory, Payment, Loyalty |
| **Phase 3** | Context Memory Layer | LangGraph + MongoDB session persistence |
| **Phase 4** | Frontend & UI | Chat + Kiosk interfaces |
| **Phase 5** | Testing & Edge Scenarios | Payment failure, order modification, out-of-stock handling |
| **Phase 6** | Optimization | Caching, response latency < 30s |

---

## 📈 Impact Metrics (Projected)

| Metric | Baseline | Post-Deployment |
|---------|-----------|----------------|
| **Conversion Rate** | 12% | **+25% (↑)** |
| **Average Order Value (AOV)** | ₹1,800 | **₹2,160 (↑20%)** |
| **Customer Retention** | 40% | **65% (↑)** |
| **Support Load** | High (manual) | **Low (AI-assisted)** |
| **Response Time** | >60s | **<10s (Real-time)** |

---

## 🧠 Future Enhancements
- 🧍‍♀️ **Virtual Stylist Agent** – Personalized outfit curation  
- 🎁 **Gift-Wrapping & Occasion Agent** – Intelligent bundling for events  
- 🕶️ **AR Try-On Integration** – Immersive shopping experience  
- 📊 **CRM Analytics Integration** – Predictive behavior modeling  


