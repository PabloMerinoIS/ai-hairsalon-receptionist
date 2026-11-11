# 💇 AI Receptionist for Hair Salons

A web chat where an **LLM-powered assistant** answers a salon's questions (prices, opening hours, FAQs) and **books, looks up and cancels real appointments** in a calendar, using tool calling.

> 🇪🇸 The interface and the assistant speak Spanish (it was built for Spanish salons). Spanish docs: [README.es.md](README.es.md).

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask&logoColor=white)
![Claude API](https://img.shields.io/badge/LLM-Claude%20API-8A2BE2?style=flat)
![Tests](https://img.shields.io/badge/tests-no%20API%20key%20needed-2EAD33?style=flat)

---

## ✨ What it does

- **Conversational booking:** the customer chats naturally; the model decides when to call tools instead of guessing.
- **Real scheduling logic:** free slots, overlap handling (capacity = number of staff), cancellation deadlines (up to 4 h before) and cancellation codes.
- **Business dashboard (`/panel`):** weekly view of appointments that refreshes itself, manual booking for phone/walk-in customers and one-click cancellation.
- **Split-screen demo (`/demo`):** customer chat on the left, the salon's calendar on the right, updating live.
- **Multi-tenant:** every salon has its own JSON file, data and calendar. A terminal wizard (`crear_negocio.py`) creates a new demo in a minute.
- **Brand colour per salon** on the clean chat page (`/chat`), meant to sit behind a "Book now" button.

## 🧠 How the assistant works

The model (Claude, via the Anthropic API) gets three tools and the salon's data as context:

| Tool | What it does |
|---|---|
| `consultar_huecos` | Returns free slots for a given day and service. Always called before proposing a time. |
| `reservar_cita` | Books an appointment once the customer confirmed date, time, service, name and phone. |
| `cancelar_cita` | Cancels an appointment given its code and the customer's phone. |

All scheduling rules live in plain Python (`agenda.py`), **not** in the prompt, so the model cannot double-book or invent free slots.

## 🏗️ Project structure

| File | Purpose |
|---|---|
| `asistente.py` | The assistant: model + tool definitions + tool-use loop. |
| `agenda.py` | Scheduling logic: slots, bookings, overlaps, cancellations, business validation. |
| `app.py` | Flask server: chat API, dashboard, rate limits and access control. |
| `negocio.json` | Example salon (hours, services, prices, staff, FAQs). Edit it to adapt the demo to another business. |
| `negocios/` | One JSON per additional salon (`estilo-luna.json` is a fictional example). |
| `crear_negocio.py` | Terminal wizard to create a new salon from questions or a price list. |
| `static/` | Sales page with embedded chat, clean chat page, dashboard and split-screen demo. |
| `test_agenda.py`, `test_panel.py` | Tests for the scheduler and the dashboard/security. |
| `render.yaml` | Deployment configuration for Render. |

## 🚀 Run it locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key"      # Windows PowerShell: $env:ANTHROPIC_API_KEY="your-key"
python app.py
```

Open http://localhost:5001 and talk to the assistant. Other pages: `/panel`, `/demo`, `/chat`.

Use another model with `export MODELO="model-name"`.

## ✅ Tests

The tests run **without an API key** and without calling the model:

```bash
python test_agenda.py
python test_panel.py
```

## 🔐 Security and cost control

- The dashboard and customer data are only reachable from your own machine. When deployed, set `ADMIN_KEY` and open `/panel?clave=YOUR_KEY`; requests without it get a 403.
- Actions that change data also require a custom header, so another website cannot trigger them from your browser (CSRF).
- Customer names are always rendered as text, never as code (XSS).
- Public demo visitors only see the appointments from **their own conversation**; demo bookings expire after 24 h.
- Rate limits protect your API spend: `LIMITE_IP_HORA` (40 messages/hour per IP) and `LIMITE_SESION` (30 per conversation). Also set a monthly spending cap in your Anthropic account.
- Appointments are stored in `citas.json`, which is git-ignored. No customer data belongs in this repository.

## 🗺️ Ideas for next steps

- Replace the JSON agenda with Google Calendar or a database (only the three public functions in `agenda.py` would change).
- WhatsApp channel through the official API.
- Reminders and no-show tracking.

---

Built by [Pablo Merino Garrido](https://github.com/PabloMerinoIS) · Data & AI Engineering student.
