# 🚑 SankatMitra – Smart Emergency Corridor System

> **AI for Bharat Hackathon 2026 — Prototype Phase Submission**
> **Team Lead:** Sanjoy Dutta

> **SankatMitra** (Friend in Distress) is a cloud-native, AI-powered platform that creates dynamic traffic corridors for ambulances across India, ensuring they reach hospitals in minimum time by clearing the path in real-time.

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Flutter (Ambulance App + Civilian App) |
| **Backend** | Python · AWS Lambda (Serverless) |
| **API** | Amazon API Gateway |
| **Database** | Amazon DynamoDB + PostgreSQL (RDS) |
| **AI/ML** | Amazon SageMaker (RNN/LSTM) + Amazon Bedrock (GenAI) |
| **Notifications** | Amazon SNS + Firebase Cloud Messaging (FCM) |
| **Security** | JWT · GPS Spoofing Detection (Anomaly Engine) |

## ✨ Key Features

- **🧠 AI Route Prediction**: Uses SageMaker-trained RNN/LSTM models to predict the most likely emergency route with high precision.
- **🌐 GenAI Multilingual Alerts**: Leverages Amazon Bedrock (Claude 3) to generate real-time, context-aware emergency alerts in **English, Hindi, and Bengali**.
- **🛡️ GPS Spoofing Detection**: Real-time anomaly detection engine to prevent malicious GPS spoofing and ensure corridor integrity.
- **⚡ Ultra-Low Latency**: Serverless architecture optimized for sub-second alert delivery via FCM.
- **📊 Real-time Dashboard**: Live tracking for ambulance operators and unified corridor management.

---

## 📁 Project Structure

```
SankatMitra/
├── ambulance_app/          # Flutter app for ambulance operators
├── civilian_app/           # Flutter app for civilian drivers
├── backend/
│   ├── lambdas/            # AWS Lambda functions (Python)
│   │   ├── auth_lambda/
│   │   ├── gps_lambda/
│   │   ├── corridor_lambda/
│   │   ├── route_lambda/
│   │   ├── alert_lambda/
│   │   └── spoofing_lambda/
│   └── shared/             # Shared Utilities (Bedrock GenAI, Models, Security)
├── ml/
│   └── rnn_model/          # RNN/LSTM SageMaker model
├── infra/
│   └── cdk/                # AWS CDK Infrastructure as Code
└── tests/
    ├── unit/
    ├── property/
    └── integration/
```

---

## 🚀 Process Flow

```
1. Ambulance Activation 🚑
    → Request Destination
    → AWS Lambda Authentication

2. AI Intelligence 🧠
    → SageMaker RNN predicts optimal route
    → Geo-spatial filtering (500m corridor radius)

3. GenAI Alert Generation 🌐
    → Amazon Bedrock generates multilingual alerts
    → (English, Hindi, Bengali)

4. Notification Delivery 📡
    → Amazon SNS + Firebase (FCM)
    → Highly targeted sub-second delivery

5. Corridor Clearance ✅
    → Real-time GPS tracking
    → Verified clearance verification
```

---

## ⚙️ Setup

### Prerequisites
- Python 3.11+
- Flutter 3.x
- AWS CLI configured
- Node.js 18+ (for CDK)

### Backend (Lambda Functions)
```bash
cd backend
pip install -r requirements-dev.txt

# Run unit tests
pytest ../tests/unit/ -v

# Run property-based tests
pytest ../tests/property/ -v
```

### Flutter Apps
```bash
# Ambulance app
cd ambulance_app
flutter pub get
flutter run

# Civilian app
cd civilian_app
flutter pub get
flutter run
```

### Infrastructure (AWS CDK)
```bash
cd infra/cdk
pip install -r requirements.txt
cdk synth
cdk deploy
```

---

## 🔐 Environment Variables

Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

---

## 🧪 Tests

| Suite | Command | Covers |
|---|---|---|
| Unit | `pytest tests/unit/ -v` | All Lambda handlers |
| Property | `pytest tests/property/ -v` | All 58 correctness properties |
| Integration | `pytest tests/integration/ -v` | End-to-end flow |

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/login` | Authenticate ambulance vehicle |
| POST | `/auth/validate` | Validate JWT token |
| POST | `/gps/update` | Submit GPS location |
| GET | `/gps/{vehicleId}` | Get current location |
| GET | `/gps/{vehicleId}/history` | Get location history |
| POST | `/corridor/activate` | Create emergency corridor |
| GET | `/corridors` | List all active corridors |
| GET | `/corridor/{id}` | Get corridor state |
| DELETE | `/corridor/{id}` | Deactivate corridor |
| PATCH | `/corridor/{id}` | Update corridor |
| POST | `/route/predict` | Predict optimal route |
| POST | `/alert/send` | Send alerts to civilians |
| POST | `/spoof/validate` | Validate GPS authenticity |

---

## 🇮🇳 Data Residency

All data stored in AWS **ap-south-1 (Mumbai)** – Indian data residency compliance.
Disaster recovery in **ap-south-2 (Hyderabad)**.

---

## 📄 License

MIT License – SankatMitra Team
