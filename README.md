# OpenF1 Live Insights (BeeWare Edition)

A Python native app using BeeWare to pull near real-time F1 race data from OpenF1 API and provide fan-focused insights. Supports live streaming and historical views on mobile (iOS/Android) and desktop.

## Setup
1. Clone the repo: `git clone https://github.com/yourusername/openf1-live-insights.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Install Briefcase: `pip install briefcase`
4. Create project scaffolds: `briefcase create` (for all platforms) or `briefcase create android` for Android.
5. For live mode: Get OpenF1 credentials (paid account for real-time) at https://tally.so/r/w2yWDb.
6. Rename `.env.example` to `.env` and fill in credentials (optional for historical).

## Usage
- **Development Mode**: `briefcase dev` (runs on desktop for testing).
- **Build & Run Mobile**:
  - Android: `briefcase build android` then `briefcase run android`.
  - iOS: `briefcase build iOS` then `briefcase run iOS` (requires macOS/Xcode).
- Enter session/meeting keys, select mode/driver/team/tire. Tabs for views (standings, laps, etc.).
- Live mode updates every 10s.
- Find keys via API: curl "https://api.openf1.org/v1/sessions?year=2025".

## Dependencies
- Python 3.10+
- See requirements.txt

## License
MIT
