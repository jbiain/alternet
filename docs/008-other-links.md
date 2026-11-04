# 008 — Other links and entry points (notes, mostly untested)

Alternet's core is carrier-independent: a site is signed, content-addressed blocks plus a manifest, so any link that can move
small messages can carry it. Status column: **tested** = shown in this project, **idea** = reasoned only.

| Link | Fit | Needs | Status |
|---|---|---|---|
| TCP over internet/Wi-Fi/hotspot (via Reticulum) | Works today | Python, a relay for cross-network | tested (Mac, iPhone, VPS) |
| `.altbundle` file by USB/SD/AirDrop | Fully offline | Nothing | tested (export/import) |
| QR codes (animated stream from screen to camera) | Offline phone-to-phone, no radio, no accounts | A small app; a page is a few KB | idea |
| LoRa radio (via Reticulum interface) | Long range, tiny rate (bytes/s) | ~$20-40 radio boards, licence-free band rules per country | idea |
| Serial / packet radio / amateur radio | Fits Reticulum | Hardware; ham licence for amateur bands | idea |
| Bluetooth / Wi-Fi Direct between phones | Local mesh | A native app (iOS Multipeer, Android Nearby); not possible from a-Shell | idea |
| Phone-line modem (dial-up/PPP) | 56 kbps, text is fine | Modem + dial-in server; landlines disappearing | idea, low priority |
| SMS gateway | Any phone, no data plan, no app | A node with a SIM/modem or a paid SMS service; read-only; gateway sees what you read | idea, best phone entry point |
| Voice call, keypad (DTMF) in, SMS or speech out | Works through every codec | VoIP number, small gateway | idea |
| Tone data over a voice call (modem-style/ggwave-style) | 50-300 bit/s realistic | Audio app on the phone; error correction | idea; first test = two phones, one call, measure bits that survive |

## Cellular (4G/5G)
Phones talk to towers, not to each other. The phone-to-phone modes that exist in the standards (sidelink/D2D) are controlled by the
carrier and chipset and are not available to apps. Licensed spectrum and SIMs belong to carriers, so we cannot transmit on it.
We can use a cellular data plan as an ordinary internet connection, which is what the relay tests did.

## Using "all the signals around"
Legal and useful: Wi-Fi networks you are allowed to join (your own, a friend's, public), Wi-Fi Direct and Bluetooth between consenting
devices, licence-free LoRa/ISM bands, and amateur radio with a licence. Not acceptable: using other people's routers, towers or
spectrum without permission. Open or public networks only carry traffic for the people who joined them.

## Order of work
1. SMS gateway design (read-only, rate-limited). 2. QR/bundle transfer. 3. Tone-over-call measurement experiment. 4. LoRa via Reticulum.
