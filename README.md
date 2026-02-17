# SankatMitra 🚑🟢  
**AI-powered real-time emergency traffic alert system** that helps create a **dynamic green corridor** for ambulances.

SankatMitra uses **GPS telemetry**, **AI-based route prediction**, and **geospatial filtering** to alert only the **relevant drivers 1–1.5 km ahead** of an approaching ambulance—reducing response time and improving emergency outcomes.

---

## ✨ What it does

When an authenticated ambulance starts an emergency run, the system:

- Tracks live GPS + speed + heading (telemetry)
- Predicts the most likely route ahead using AI/ETA logic
- Filters users **by direction + proximity**
- Sends alerts to vehicles **only in the ambulance’s path**
- Continuously updates the “green corridor” as the ambulance moves

---

## ✅ Key Benefits

- **Early awareness** for drivers ahead  
- **Direction-based filtering** (no unnecessary noise)
- **Reduced response time** for ambulances
- **Secure authentication** for verified emergency vehicles

---

## 🔥 Core Features

- **Real-time GPS tracking** (ambulance telemetry streaming)
- **Dynamic route prediction** (AI/heuristics)
- **Geospatial filtering** (only 1–1.5 km corridor recipients)
- **Driver notifications** (push/SMS/app alert)
- **Admin / Authority dashboard** (monitor emergency runs)
- **Vehicle verification & secure onboarding**
- **Audit logs** for safety and compliance

---

## 🧠 How the corridor filtering works (high-level)

1. Ambulance sends telemetry (lat, lng, speed, heading)
2. System predicts next road segments (route prediction)
3. Builds a corridor polygon / buffered path (1–1.5 km ahead)
4. Selects drivers who are:
   - Inside corridor buffer
   - Moving in the same direction OR on intersecting path
5. Sends alerts with distance + ETA + action (“Give way / move left”)

---

## 🏗️ Suggested Architecture (Reference)

- **Ambulance App / GPS Device** → telemetry stream
- **Backend API** → auth + data processing
- **AI/Route Engine** → route prediction + ETA
- **Geo Engine** (PostGIS / H3 / GeoHash) → filtering
- **Notification Service** (FCM / APNS / SMS) → alerts
- **Dashboard** → monitoring + analytics

---

## 🧰 Tech Stack (recommended)

You can adjust this section to match your actual implementation.

**Backend**
- Node.js / Python (FastAPI)
- Redis (real-time caching)
- PostgreSQL + PostGIS (geospatial queries)

**AI / Routing**
- OSRM / Mapbox / Google Routes API (optional)
- ML model (optional) for route prediction

**Realtime**
- WebSockets / MQTT / Kafka (optional)

**Notifications**
- Firebase Cloud Messaging (FCM) / SMS gateway

**Infra**
- AWS (API Gateway, EC2/ECS, RDS, ElastiCache, CloudWatch)

---

## 🚀 Getting Started (Template)

> Update commands below based on your repo structure.

### 1) Clone the repo
```bash
git clone https://github.com/sanjaygitdutta/SankatMitra
cd SankatMitra
