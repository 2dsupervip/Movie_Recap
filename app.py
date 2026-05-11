import streamlit as st
import os
import json
import urllib.request
import subprocess
import yt_dlp
import google.generativeai as genai
from groq import Groq
from faster_whisper import WhisperModel

# --- 🌟 Page Configuration & UI ---
st.set_page_config(page_title="Recap Studio Pro", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .main-title { font-size: 32px; font-weight: 800; color: #00E676; text-align: center; margin-bottom: 5px; }
    .sub-title { text-align: center; color: #A0A0A0; font-size: 14px; margin-bottom: 30px; font-family: monospace;}
    .step-header { color: #00E676; font-weight: bold; font-size: 20px; border-bottom: 1px solid #00E676; padding-bottom: 10px; margin-bottom: 15px; margin-top: 20px;}
    .stButton>button { background-color: #00E676; color: #111111; font-weight: bold; border-radius: 8px; width: 100%; transition: 0.3s; }
    .stButton>button:hover { background-color: #B2FF59; color: #000000; }
    </style>
""", unsafe_allow_html=True)

# --- Persistent API Storage ---
API_FILE = "api_config.json"
def load_keys():
    if os.path.exists(API_FILE):
        with open(API_FILE, "r") as f: return json.load(f)
    return {"gemini_key": "", "groq_key": ""}

def save_keys(keys_dict):
    with open(API_FILE, "w") as f: json.dump(keys_dict, f)

saved_keys = load_keys()
if 'gemini_key' not in st.session_state: st.session_state.gemini_key = saved_keys.get("gemini_key", "")
if 'groq_key' not in st.session_state: st.session_state.groq_key = saved_keys.get("groq_key", "")
if 'eng_text' not in st.session_state: st.session_state.eng_text = ""
if 'mm_text' not in st.session_state: st.session_state.mm_text = ""

# --- Helper Functions ---
def get_video_duration(video_path):
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{video_path}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try: return float(result.stdout.strip())
    except: return 1.0

def ensure_myanmar_font():
    font_path = "Padauk.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/padauk/Padauk-Regular.ttf"
        urllib.request.urlretrieve(url, font_path)
    return font_path

def get_prompt(duration_seconds, tone, transcript):
    word_limit = int((duration_seconds / 60) * 135)
    return f"""Act as a professional movie recapper. Summarize this English transcription into a natural Burmese storytelling script.
TONE: {tone}
LENGTH: ~{word_limit} Burmese words (Crucial for audio sync, video is {duration_seconds:.1f}s).
CRITICAL INSTRUCTIONS:
1. Do NOT include English names in parentheses. Write names naturally in Burmese only (e.g., write "ဂျက်", NOT "ဂျက် (Jack)").
2. Write in a conversational, voice-over ready flow.

Transcription:
{transcript}"""

# --- 🎛️ SIDEBAR SETTINGS ---
with st.sidebar:
    st.title("⚙️ Studio Settings")
    with st.expander("🔑 API Keys", expanded=True):
        st.session_state.groq_key = st.text_input("Groq API Key (For Fast Whisper)", type="password", value=st.session_state.groq_key)
        st.session_state.gemini_key = st.text_input("Gemini API Key (For Translation)", type="password", value=st.session_state.gemini_key)
        if st.button("💾 Save Keys"):
            save_keys({"gemini_key": st.session_state.gemini_key, "groq_key": st.session_state.groq_key})
            st.success("Saved!")
            
    st.markdown("---")
    st.subheader("🗣️ Render Preferences")
    voice_choice = st.radio("AI Voice:", ["👨 Male (Thiha)", "👩 Female (Nilar)"])
    use_bgm = st.checkbox("🎶 Add Background Music", value=True)
    if use_bgm:
        st.info("💡 'bgm.mp3' ဖိုင်ကို project folder ထဲ ထည့်ထားပေးပါ။")

# --- 🎬 MAIN UI ---
st.markdown('<div class="main-title">🎬 Shorts Movie Recap Studio</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Groq + Faster-Whisper | Auto Sync | Blur & Hardsubs</div>', unsafe_allow_html=True)

col1, col2 = st.columns([1, 1.2], gap="large")

# ==========================================
# LEFT COLUMN: MEDIA & TRANSCRIPTION
# ==========================================
with col1:
    st.markdown('<div class="step-header">Step 1: Media & Audio Extract</div>', unsafe_allow_html=True)
    input_method = st.radio("Media Source:", ["Upload Video", "YouTube Link"], horizontal=True)
    
    video_ready = False
    if input_method == "Upload Video":
        uploaded_file = st.file_uploader("ဗီဒီယိုဖိုင် ရွေးပါ", type=["mp4", "mov"])
        if uploaded_file:
            with open("input_video.mp4", "wb") as f: f.write(uploaded_file.getbuffer())
            st.video("input_video.mp4")
            video_ready = True
    else:
        youtube_url = st.text_input("YouTube Link")
        if st.button("⬇️ Download YouTube Video"):
            with st.spinner("Downloading..."):
                try:
                    with yt_dlp.YoutubeDL({'format': 'best[height<=720]', 'outtmpl': 'input_video.mp4', 'quiet': True}) as ydl: ydl.download([youtube_url])
                    st.success("Download Complete!")
                except Exception as e: st.error(f"Error: {e}")
        if os.path.exists("input_video.mp4"): video_ready = True

    if video_ready:
        st.markdown('<div class="step-header">Step 2: English Transcription</div>', unsafe_allow_html=True)
        transcribe_engine = st.radio("Transcription Engine:", ["⚡ Groq API (Super Fast)", "🐢 Faster-Whisper (No API, Local)"], horizontal=True)
        
        if st.button("🎙️ Extract Audio to Text"):
            with st.spinner("Extracting audio and transcribing..."):
                subprocess.run('ffmpeg -y -i input_video.mp4 -vn -acodec libmp3lame -ar 16000 -ac 1 temp_audio.mp3', shell=True)
                
                if "Groq" in transcribe_engine:
                    if not st.session_state.groq_key: st.error("Groq API Key လိုအပ်ပါသည်!")
                    else:
                        client = Groq(api_key=st.session_state.groq_key)
                        with open("temp_audio.mp3", "rb") as f:
                            st.session_state.eng_text = client.audio.transcriptions.create(file=("temp_audio.mp3", f.read()), model="whisper-large-v3", response_format="text")
                        st.success("Groq မှ စာသားထုတ်ယူပြီးပါပြီ!")
                else:
                    model = WhisperModel("small", compute_type="int8") 
                    segments, _ = model.transcribe("temp_audio.mp3")
                    st.session_state.eng_text = " ".join([s.text for s in segments])
                    st.success("Faster-Whisper မှ စာသားထုတ်ယူပြီးပါပြီ!")

        st.session_state.eng_text = st.text_area("🇺🇸 English Transcript:", value=st.session_state.eng_text, height=150)

# ==========================================
# RIGHT COLUMN: SCRIPT & RENDER
# ==========================================
with col2:
    st.markdown('<div class="step-header">Step 3: Burmese Scripting</div>', unsafe_allow_html=True)
    script_tone = st.selectbox("📝 Tone", ["storytelling", "calm", "energetic", "dramatic"])
    
    col_auto, col_manual = st.columns(2)
    if col_auto.button("🚀 Auto Generate (Gemini)"):
        if not st.session_state.gemini_key or not st.session_state.eng_text:
            st.warning("Gemini API Key နှင့် English Script လိုအပ်ပါသည်!")
        else:
            with st.spinner("Gemini မှ ဇာတ်ညွှန်းရေးဆွဲနေသည်..."):
                try:
                    vid_duration = get_video_duration("input_video.mp4")
                    prompt = get_prompt(vid_duration, script_tone, st.session_state.eng_text)
                    genai.configure(api_key=st.session_state.gemini_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    st.session_state.mm_text = model.generate_content(prompt).text
                    st.success("ဇာတ်ညွှန်း အသင့်ဖြစ်ပါပြီ!")
                except Exception as e: st.error(f"Error: {e}")

    if col_manual.button("📋 Copy Manual Prompt"):
        vid_duration = get_video_duration("input_video.mp4")
        st.info("အောက်ပါ Prompt ကို ကူးယူပြီး ChatGPT/Gemini တွင် ထည့်ပါ။")
        st.code(get_prompt(vid_duration, script_tone, st.session_state.eng_text))

    st.session_state.mm_text = st.text_area("🇲🇲 Burmese Script (Editor):", value=st.session_state.mm_text, height=200)

    st.markdown('<div class="step-header">Step 4: Pro Video Rendering</div>', unsafe_allow_html=True)
    
    if st.button("🎬 RENDER PRO VIDEO", type="primary", use_container_width=True):
        if not os.path.exists("input_video.mp4") or not st.session_state.mm_text.strip():
            st.error("ဗီဒီယို နှင့် မြန်မာဇာတ်ညွှန်း လိုအပ်ပါသည်!")
        else:
            progress_bar = st.progress(0, text="Starting Pro Render Engine...")
            
            # --- 1. TTS & Clean SRT Output ---
            progress_bar.progress(20, text="Step 1: AI အသံနှင့် စာတန်းထိုး (SRT) ထုတ်လုပ်နေသည်...")
            voice_id = "my-MM-ThihaNeural" if "Male" in voice_choice else "my-MM-NilarNeural"
            
            with open("script.txt", "w", encoding="utf-8") as f: f.write(st.session_state.mm_text)
            # Edge-TTS CLI is 100% stable for SRT generation
            subprocess.run(f'edge-tts --file script.txt --voice {voice_id} --write-media final_voice.mp3 --write-subtitles subtitles.srt', shell=True)
            
            # --- 2. Elastic Sync (Speed adjustment) ---
            progress_bar.progress(40, text="Step 2: Video နှင့် Audio အရှည် ကွက်တိဖြစ်အောင် ညှိနေသည်...")
            vid_dur = get_video_duration("input_video.mp4")
            aud_dur = get_video_duration("final_voice.mp3")
            speed_ratio = vid_dur / aud_dur if aud_dur > 0 else 1.0
            
            # --- 3. FFmpeg Complex Filter (Crop + Mirror + Blur + Subtitles + BGM) ---
            progress_bar.progress(70, text="Step 3: Effect များထည့်ခြင်းနှင့် မြန်မာဖောင့်စာတန်းထိုးနေသည်...")
            ensure_myanmar_font()
            
            # Master Video Filter Graph
            v_filter = (
                f"[0:v]setpts={speed_ratio}*PTS,hflip," # Sync & Mirror
                f"crop=iw*0.94:ih*0.94:iw*0.03:ih*0.03,scale=-2:720," # Crop 3% & Resize
                f"split[v1][v2];"
                f"[v1]crop=iw:ih*0.25:0:ih*0.75,boxblur=20:5[blurred];" # Bottom 25% Blur
                f"[v2][blurred]overlay=0:main_h-overlay_h[vblur];"
                f"[vblur]subtitles=subtitles.srt:fontsdir=.:force_style='Fontname=Padauk,Fontsize=22,PrimaryColour=&H00FFFF,Outline=1,BorderStyle=1'[vout]"
            )

            if use_bgm and os.path.exists("bgm.mp3"):
                # Audio Filter with BGM
                a_filter = "[1:a]volume=1.0[a1];[2:a]volume=0.10[a2];[a1][a2]amix=inputs=2:duration=first[aout]"
                cmd = f'ffmpeg -y -i input_video.mp4 -i final_voice.mp3 -stream_loop -1 -i bgm.mp3 -filter_complex "{v_filter};{a_filter}" -map "[vout]" -map "[aout]" -c:v libx264 -preset fast -c:a aac -shortest final_merged.mp4'
            else:
                cmd = f'ffmpeg -y -i input_video.mp4 -i final_voice.mp3 -filter_complex "{v_filter}" -map "[vout]" -map 1:a -c:v libx264 -preset fast -c:a aac -shortest final_merged.mp4'

            subprocess.run(cmd, shell=True)
            
            progress_bar.progress(100, text="✅ Render ပြီးဆုံးပါပြီ!")
            st.success("🎉 ဗီဒီယိုနှင့် စာတန်းထိုး အသင့်ဖြစ်ပါပြီ!")
            st.video("final_merged.mp4")

            # --- 📥 Clean Download Section ---
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                with open("final_merged.mp4", "rb") as f:
                    st.download_button("📥 Download Final Video", data=f, file_name="Final_Pro_Recap.mp4", mime="video/mp4")
            with col_d2:
                if os.path.exists("subtitles.srt"):
                    with open("subtitles.srt", "rb") as f:
                        st.download_button("📝 Download SRT", data=f, file_name="Subtitles.srt", mime="text/plain")
