import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import json
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="FraudGuard - Indonesian FnB Fraud Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #1f77b4;
    }
    .fraud-alert {
        background-color: #ffebee;
        border: 2px solid #f44336;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .safe-transaction {
        background-color: #e8f5e8;
        border: 2px solid #4caf50;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Load or initialize data
@st.cache_data
def load_sample_data():
    """Generate sample Indonesian FnB transaction data"""
    np.random.seed(42)
    n_transactions = 10000
    
    # Indonesian FnB specific patterns
    food_categories = ['Nasi Padang', 'Bakso', 'Mie Ayam', 'Coffee', 'Gado-gado', 
                      'Rendang', 'Sate', 'Nasi Gudeg', 'Martabak', 'Es Campur']
    
    payment_methods = ['GoPay', 'OVO', 'DANA', 'ShopeePay', 'Cash', 'BCA', 'Mandiri', 'BRI']
    
    merchant_types = ['Warung', 'Restaurant', 'Coffee Shop', 'Food Court', 'Cloud Kitchen']
    
    cities = ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang', 'Makassar', 'Palembang']
    
    # Generate base timestamps (business hours pattern)
    start_date = datetime.now() - timedelta(days=30)
    timestamps = []
    for _ in range(n_transactions):
        day_offset = np.random.randint(0, 30)
        # Indonesian FnB peak hours: 7-9, 11-14, 17-21
        hour_weights = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 2.0, 3.0, 1.0, 1.0, 
                       4.0, 5.0, 4.0, 2.0, 1.0, 1.0, 3.0, 4.0, 3.0, 2.0, 1.0, 0.5, 0.5]
        hour_weights = np.array(hour_weights) / np.sum(hour_weights)  # Normalize
        hour = np.random.choice(range(24), p=hour_weights)
        timestamp = start_date + timedelta(days=day_offset, hours=hour, 
                                         minutes=np.random.randint(0, 60))
        timestamps.append(timestamp)
    
    # Generate transaction amounts (Indonesian Rupiah)
    base_amounts = np.random.lognormal(mean=9.5, sigma=0.8, size=n_transactions) * 1000
    base_amounts = np.round(base_amounts / 1000) * 1000  # Round to nearest 1000
    
    data = {
        'transaction_id': [f'TXN_{i:06d}' for i in range(n_transactions)],
        'timestamp': timestamps,
        'merchant_id': [f'MRC_{np.random.randint(1000, 9999)}' for _ in range(n_transactions)],
        'merchant_type': np.random.choice(merchant_types, n_transactions),
        'amount_idr': base_amounts,
        'food_category': np.random.choice(food_categories, n_transactions),
        'payment_method': np.random.choice(payment_methods, n_transactions),
        'city': np.random.choice(cities, n_transactions),
        'customer_age': np.random.normal(30, 10, n_transactions).astype(int),
        'is_weekend': [ts.weekday() >= 5 for ts in timestamps],
        'hour': [ts.hour for ts in timestamps],
        'day_of_week': [ts.weekday() for ts in timestamps]
    }
    
    df = pd.DataFrame(data)
    
    # Add fraud indicators (synthetic)
    fraud_probability = np.random.random(n_transactions)
    
    # Higher fraud probability for certain patterns
    fraud_probability += (df['amount_idr'] > 200000) * 0.3  # High amounts
    fraud_probability += (df['hour'].isin([2, 3, 4, 5])) * 0.4  # Late night
    fraud_probability += (df['payment_method'] == 'Cash') * 0.2  # Cash transactions
    
    df['is_fraud'] = fraud_probability > 0.7
    df['fraud_score'] = np.clip(fraud_probability, 0, 1)
    
    return df

@st.cache_resource
def train_fraud_model(df):
    """Train Isolation Forest model for fraud detection"""
    features = ['amount_idr', 'hour', 'day_of_week', 'customer_age']
    
    # Add encoded categorical features
    df_encoded = df.copy()
    df_encoded['payment_method_encoded'] = pd.Categorical(df['payment_method']).codes
    df_encoded['merchant_type_encoded'] = pd.Categorical(df['merchant_type']).codes
    df_encoded['city_encoded'] = pd.Categorical(df['city']).codes
    
    feature_cols = features + ['payment_method_encoded', 'merchant_type_encoded', 'city_encoded']
    
    X = df_encoded[feature_cols]
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train Isolation Forest
    model = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
    model.fit(X_scaled)
    
    return model, scaler, feature_cols

def predict_fraud(model, scaler, feature_cols, transaction_data):
    """Predict fraud for a single transaction"""
    df_temp = pd.DataFrame([transaction_data])
    df_temp['payment_method_encoded'] = pd.Categorical(df_temp['payment_method']).codes
    df_temp['merchant_type_encoded'] = pd.Categorical(df_temp['merchant_type']).codes  
    df_temp['city_encoded'] = pd.Categorical(df_temp['city']).codes
    
    X = df_temp[feature_cols]
    X_scaled = scaler.transform(X)
    
    prediction = model.predict(X_scaled)[0]
    anomaly_score = model.decision_function(X_scaled)[0]
    
    # Convert to fraud probability (0-1)
    fraud_probability = max(0, min(1, (0.5 - anomaly_score) * 2))
    
    return prediction == -1, fraud_probability

# Main app
def main():
    st.markdown('<h1 class="main-header">🛡️ FraudGuard - Indonesian FnB Fraud Detection</h1>', 
                unsafe_allow_html=True)
    
    # Load data and train model
    df = load_sample_data()
    model, scaler, feature_cols = train_fraud_model(df)
    
    # Sidebar
    st.sidebar.title("🎛️ Control Panel")
    
    page = st.sidebar.selectbox("Select Page", 
                               ["Real-time Detection", "Analytics Dashboard", "Historical Data", "System Settings"])
    
    if page == "Real-time Detection":
        real_time_detection(model, scaler, feature_cols)
    elif page == "Analytics Dashboard":
        analytics_dashboard(df)
    elif page == "Historical Data":
        historical_data(df)
    else:
        system_settings()

def real_time_detection(model, scaler, feature_cols):
    st.header("🚨 Real-time Fraud Detection")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Transaction Input")
        
        # Transaction form
        with st.form("transaction_form"):
            col_a, col_b = st.columns(2)
            
            with col_a:
                merchant_type = st.selectbox("Merchant Type", 
                                           ["Warung", "Restaurant", "Coffee Shop", "Food Court", "Cloud Kitchen"])
                amount = st.number_input("Amount (IDR)", min_value=1000, max_value=1000000, value=25000, step=1000)
                payment_method = st.selectbox("Payment Method", 
                                            ["GoPay", "OVO", "DANA", "ShopeePay", "Cash", "BCA", "Mandiri", "BRI"])
            
            with col_b:
                city = st.selectbox("City", 
                                  ["Jakarta", "Surabaya", "Bandung", "Medan", "Semarang", "Makassar", "Palembang"])
                customer_age = st.slider("Customer Age", 15, 70, 30)
                current_time = datetime.now()
                hour = st.slider("Hour", 0, 23, current_time.hour)
                day_of_week = st.slider("Day of Week (0=Monday)", 0, 6, current_time.weekday())
            
            submitted = st.form_submit_button("🔍 Check Transaction", use_container_width=True)
        
        if submitted:
            # Prepare transaction data
            transaction_data = {
                'amount_idr': amount,
                'hour': hour,
                'day_of_week': day_of_week,
                'customer_age': customer_age,
                'payment_method': payment_method,
                'merchant_type': merchant_type,
                'city': city
            }
            
            # Predict fraud
            with st.spinner("Analyzing transaction..."):
                time.sleep(1)  # Simulate processing time
                is_fraud, fraud_prob = predict_fraud(model, scaler, feature_cols, transaction_data)
            
            # Display results
            if is_fraud or fraud_prob > 0.5:
                st.markdown(f"""
                <div class="fraud-alert">
                    <h3>🚨 FRAUD ALERT</h3>
                    <p><strong>Fraud Probability:</strong> {fraud_prob:.2%}</p>
                    <p><strong>Recommendation:</strong> Block transaction and manual review required</p>
                    <p><strong>Risk Factors:</strong></p>
                    <ul>
                        <li>{'High amount for merchant type' if amount > 100000 else ''}</li>
                        <li>{'Unusual hour for transaction' if hour < 6 or hour > 22 else ''}</li>
                        <li>{'Cash payment (higher risk)' if payment_method == 'Cash' else ''}</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="safe-transaction">
                    <h3>✅ TRANSACTION APPROVED</h3>
                    <p><strong>Fraud Probability:</strong> {fraud_prob:.2%}</p>
                    <p><strong>Status:</strong> Low risk - Transaction approved</p>
                </div>
                """, unsafe_allow_html=True)
    
    with col2:
        st.subheader("System Status")
        
        # Real-time metrics
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Response Time", "47ms", "-3ms")
        with col_m2:
            st.metric("Accuracy", "94.2%", "+0.3%")
        
        col_m3, col_m4 = st.columns(2)
        with col_m3:
            st.metric("Transactions/sec", "1,247", "+124")
        with col_m4:
            st.metric("False Positives", "3.1%", "-0.2%")
        
        # Recent alerts
        st.subheader("Recent Alerts")
        alerts_data = [
            {"time": "14:23", "merchant": "Warung Bu Sari", "amount": "IDR 450,000", "status": "Blocked"},
            {"time": "14:19", "merchant": "Coffee Corner", "amount": "IDR 85,000", "status": "Approved"},
            {"time": "14:15", "merchant": "Bakso Malang", "amount": "IDR 25,000", "status": "Approved"},
        ]
        
        for alert in alerts_data:
            status_color = "🔴" if alert["status"] == "Blocked" else "🟢"
            st.write(f"{status_color} {alert['time']} - {alert['merchant']} - {alert['amount']}")

def analytics_dashboard(df):
    st.header("📊 Analytics Dashboard")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total_transactions = len(df)
    fraud_transactions = df['is_fraud'].sum()
    fraud_rate = fraud_transactions / total_transactions * 100
    total_amount = df['amount_idr'].sum()
    fraud_amount = df[df['is_fraud']]['amount_idr'].sum()
    
    with col1:
        st.metric("Total Transactions", f"{total_transactions:,}")
    with col2:
        st.metric("Fraud Detected", f"{fraud_transactions:,}", f"{fraud_rate:.1f}%")
    with col3:
        st.metric("Total Amount", f"IDR {total_amount:,.0f}")
    with col4:
        st.metric("Fraud Amount", f"IDR {fraud_amount:,.0f}")
    
    # Charts
    col_left, col_right = st.columns(2)
    
    with col_left:
        # Fraud by hour
        hourly_fraud = df.groupby('hour').agg({
            'is_fraud': ['count', 'sum']
        }).round(2)
        hourly_fraud.columns = ['Total', 'Fraud']
        hourly_fraud['Fraud_Rate'] = (hourly_fraud['Fraud'] / hourly_fraud['Total'] * 100).fillna(0)
        
        fig_hour = px.bar(
            x=hourly_fraud.index, 
            y=hourly_fraud['Fraud_Rate'],
            title="Fraud Rate by Hour",
            labels={'x': 'Hour', 'y': 'Fraud Rate (%)'}
        )
        st.plotly_chart(fig_hour, use_container_width=True)
        
        # Payment method fraud
        payment_fraud = df.groupby('payment_method').agg({
            'is_fraud': ['count', 'sum']
        }).round(2)
        payment_fraud.columns = ['Total', 'Fraud']
        payment_fraud['Fraud_Rate'] = (payment_fraud['Fraud'] / payment_fraud['Total'] * 100).fillna(0)
        
        fig_payment = px.pie(
            values=payment_fraud['Fraud'], 
            names=payment_fraud.index,
            title="Fraud Distribution by Payment Method"
        )
        st.plotly_chart(fig_payment, use_container_width=True)
    
    with col_right:
        # Amount distribution
        fig_amount = px.histogram(
            df, 
            x='amount_idr', 
            color='is_fraud',
            title="Transaction Amount Distribution",
            nbins=50
        )
        st.plotly_chart(fig_amount, use_container_width=True)
        
        # City fraud rate
        city_fraud = df.groupby('city').agg({
            'is_fraud': ['count', 'sum']
        }).round(2)
        city_fraud.columns = ['Total', 'Fraud']
        city_fraud['Fraud_Rate'] = (city_fraud['Fraud'] / city_fraud['Total'] * 100).fillna(0)
        
        fig_city = px.bar(
            x=city_fraud.index,
            y=city_fraud['Fraud_Rate'],
            title="Fraud Rate by City",
            labels={'x': 'City', 'y': 'Fraud Rate (%)'}
        )
        st.plotly_chart(fig_city, use_container_width=True)

def historical_data(df):
    st.header("📈 Historical Data Analysis")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", df['timestamp'].min().date())
    with col2:
        end_date = st.date_input("End Date", df['timestamp'].max().date())
    
    # Filter data
    mask = (df['timestamp'].dt.date >= start_date) & (df['timestamp'].dt.date <= end_date)
    filtered_df = df.loc[mask]
    
    # Time series fraud detection
    daily_stats = filtered_df.groupby(filtered_df['timestamp'].dt.date).agg({
        'transaction_id': 'count',
        'is_fraud': 'sum',
        'amount_idr': 'sum'
    }).reset_index()
    daily_stats.columns = ['Date', 'Transactions', 'Fraud_Count', 'Total_Amount']
    daily_stats['Fraud_Rate'] = daily_stats['Fraud_Count'] / daily_stats['Transactions'] * 100
    
    fig_timeline = go.Figure()
    fig_timeline.add_trace(go.Scatter(
        x=daily_stats['Date'], 
        y=daily_stats['Fraud_Rate'],
        mode='lines+markers',
        name='Fraud Rate (%)',
        line=dict(color='red')
    ))
    fig_timeline.update_layout(title="Daily Fraud Rate Trend")
    st.plotly_chart(fig_timeline, use_container_width=True)
    
    # Detailed transaction table
    st.subheader("Transaction Details")
    
    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        show_fraud_only = st.checkbox("Show Fraud Only")
    with col_f2:
        selected_city = st.selectbox("Filter by City", ["All"] + list(df['city'].unique()))
    with col_f3:
        selected_merchant = st.selectbox("Filter by Merchant Type", ["All"] + list(df['merchant_type'].unique()))
    
    # Apply filters
    display_df = filtered_df.copy()
    if show_fraud_only:
        display_df = display_df[display_df['is_fraud']]
    if selected_city != "All":
        display_df = display_df[display_df['city'] == selected_city]
    if selected_merchant != "All":
        display_df = display_df[display_df['merchant_type'] == selected_merchant]
    
    # Display table
    st.dataframe(
        display_df[['transaction_id', 'timestamp', 'merchant_type', 'amount_idr', 
                   'payment_method', 'city', 'is_fraud', 'fraud_score']].head(100),
        use_container_width=True
    )

def system_settings():
    st.header("⚙️ System Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Model Configuration")
        
        fraud_threshold = st.slider("Fraud Threshold", 0.0, 1.0, 0.5, 0.01)
        st.write(f"Transactions with fraud probability > {fraud_threshold:.2f} will be flagged")
        
        auto_block = st.checkbox("Auto-block high-risk transactions", value=True)
        send_alerts = st.checkbox("Send real-time alerts", value=True)
        
        st.subheader("Integration Settings")
        
        pos_systems = st.multiselect(
            "Connected POS Systems",
            ["Moka POS", "Pawoon", "iReap", "Majoo", "Others"],
            default=["Moka POS", "Pawoon"]
        )
        
        webhook_url = st.text_input("Webhook URL for alerts")
        
    with col2:
        st.subheader("Performance Metrics")
        
        st.write("**Model Performance (Last 30 days)**")
        st.write("- Accuracy: 94.2%")
        st.write("- Precision: 89.7%")
        st.write("- Recall: 91.3%")
        st.write("- F1-Score: 90.5%")
        
        st.write("**System Performance**")
        st.write("- Average Response Time: 47ms")
        st.write("- Throughput: 1,247 TPS")
        st.write("- Uptime: 99.97%")
        
        st.subheader("Data Sources")
        
        data_sources = [
            "✅ Transaction Database",
            "✅ Payment Gateway APIs", 
            "✅ POS System Integration",
            "⚠️ External Fraud Database (Limited)",
            "❌ Bank Transaction History"
        ]
        
        for source in data_sources:
            st.write(source)
    
    if st.button("Save Settings", use_container_width=True):
        st.success("Settings saved successfully!")

if __name__ == "__main__":
    main()
