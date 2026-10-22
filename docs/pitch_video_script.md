# UNICEF Venture Fund pitch video: script (2:00)

Rules from the form: no more than 2 minutes, in English or with English subtitles, the real team speaking for themselves, and the product shown working through a live demo or screen recording. No AI avatars, synthetic voices or AI-generated footage. Upload to YouTube; unlisted is fine.

About 280 spoken words. At a calm pace (about 140 words per minute) that leaves a few seconds of buffer.

| Time | Speaker / on screen | Words |
|---|---|---|
| 0:00–0:20 | **Linda** on camera | "Hello, I'm Linda Chibututu, founder and CEO of Zuri Circle in Nigeria. In our communities, pregnancy danger signs are too often recognised too late: a headache that is really a warning, bleeding that waits until morning, a clinic nobody knows how to reach." |
| 0:20–0:35 | **Linda** on camera | "Data is expensive and connections are weak, so heavy apps don't reach these women. That's why we built ZuriTrustAI, an open-source assistant that works on WhatsApp and a very light web page." |
| 0:35–1:10 | **Screen recording**, voice-over by Linda or the developer | "Here it is working today. A woman types, in her own words: 'My head hurts and my vision is blurry.' ZuriTrustAI recognises a danger sign, severe headache with blurred vision, and tells her to go to a hospital now. She replies 'Lagos', and it shows 24-hour facilities that can handle emergencies. If she simply asks 'what should I eat?', she gets a short answer from our reviewed knowledge base, with its source. It never diagnoses. It helps her act in time." |
| 1:10–1:30 | **Dr. Rana** on camera | "I'm Dr. Masud Rana from Lamar University, technical advisor. The screening rules are transparent, and we test them on cases the system has never seen. When that testing found gaps, we fixed them, and every change is now checked automatically. All the code is open source on GitHub." |
| 1:30–1:42 | **Dr. Tsado** on camera | "I'm Dr. Lucy Tsado. Privacy is built in: we don't store message text, phone numbers are replaced with secure codes, and anyone can delete their session at any time." |
| 1:42–2:00 | **Linda** on camera | "Zuri Circle already serves 1,426 verified women across three countries. With 100,000 dollars from UNICEF, in twelve months we will complete clinical review, pilot ZuriTrustAI, and reach 5,000 women in three new markets. Help us make sure no mother waits too long. Thank you." |

## Demo recording steps (35 seconds)
1. Run the app (`python -m app.main`) and open `http://127.0.0.1:8000` in a phone-sized browser window, or use the WhatsApp test number.
2. Type: `My head hurts and my vision is blurry`, then send. Pause 2 seconds on the red reply.
3. Type: `Lagos`, then send. Pause on the facility list.
4. Type: `what should I eat`, then send. Pause on the answer showing its source.
5. Optional: after the danger warning, reply `5` to show the hand-off to a Zuri Circle health professional.
6. Optional: reply `4`, then `JOIN`, to show the 90-day execution track.

## Before recording
- Replace the sample facilities with real, verified ones, or keep the on-screen "(placeholder)" labels visible so nothing looks like real data.
- Confirm that Lamar University has approved Dr. Rana and Dr. Tsado appearing in the video.
- Check every number in the script against company records (1,426 users, three countries, USD 100,000, 5,000 women).
- Record in a quiet room, landscape, eye level. Add English subtitles.
