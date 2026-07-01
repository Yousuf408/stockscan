# TradeSentry — 5-Min Yahoo Finance Data Fetcher

Yeh script humne discuss kiye `vol_ratio` timing-lag problem ko backtest karne
ke liye hai. Isko apne GitHub repo mein (ya kahi bhi jahan internet unrestricted ho)
run karo.

## Kya karta hai

`stocks.txt` mein diye 248 stocks ke liye Yahoo Finance se pichle 60 din ka
5-minute interval OHLCV data download karta hai, aur har stock ki alag CSV
`output/` folder mein save karta hai.

Har file mein yeh columns honge:

| column | meaning |
|---|---|
| `stock` | symbol (bina .NS ke) |
| `date` | trading date |
| `time` | HH:MM (candle start time) |
| `Open/High/Low/Close` | us 5-min candle ka price |
| `Volume` | sirf us 5-min candle ka volume |
| `cum_volume` | **din ki shuruaat se ab tak ka running total volume** — yeh column hi hume chahiye tha, kyunki aapka scanner bhi cumulative volume use karta hai |

Ek extra file `output/_combined_daily_cumvol.csv` bhi banegi jisme sab stocks
ka data ek saath hoga — analysis ke liye yeh sabse useful hoga.

## Kaise run karein

```bash
pip install -r requirements.txt
python fetch_5min_data.py
```

~250 stocks, 1.2 sec delay ke saath — poora chalne mein **6-8 minute** lagenge.
Beech mein internet gaya ya script fail hui toh dobara run karo — jo stocks
already fetch ho chuki hain unhe skip kar dega (`output/` mein file check karta hai).

Optional flags:
```bash
python fetch_5min_data.py --period 60d --interval 5m --sleep 1.5
```

## Important limitation

Yahoo Finance sirf **pichle ~60 calendar din** ka 5-min data deta hai — usse
purana data available hi nahi hota, yeh Yahoo ka hard limit hai, script ka
nahi.

## Isके baad kya karna hai

Jab yeh data mil jaye, mujhe `output/_combined_daily_cumvol.csv` bhejo
(ya iska ek trimmed version, kyunki poori file bahut badi ho sakti hai).
Uske baad main:

1. Har stock ke liye "typical cum_volume by time-of-day" baseline banaunga
   (jaise: "9:35 AM tak is stock ka average cum_volume kitna hota hai,
   pichle 5-10 trading din ke hisaab se")
2. Us naye baseline ko humare existing signal data (jo humne pehle discuss
   kiya) ke against test karunga
3. Dekhenge ki isse `vol_ratio` ka lag kam hota hai ya nahi — real backtest
   ke through, guess se nahi

Agar file bahut badi ho GitHub/upload ke liye, sirf yeh stocks bhejna kaafi
hoga jo humne already discuss kiye: `SGFIN, RAMCOSYS, FAIRCHEMOR, EIMCOELECO,
VELJAN, DIVGIITTS, THEJO` — inhi 7-8 stocks se pehle validate kar lete hain
ki naya baseline kaam kar raha hai ya nahi, phir poore 248 pe scale karenge.
