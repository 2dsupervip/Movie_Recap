import streamlit as st
import os
import gc
import uuid
import asyncio
import subprocess
import json
import zipfile
import google.generativeai as genai
from groq import Groq
import edge_tts
import yt_dlp
from gtts import gTTS

# --- Multi-user Session Setup ---
if 'sid' not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())[:8]

def fpath(filename):
    """User တစ်ယောက်ချင်းစီအတွက် သီးသန့် ဖိုင်နာမည်များ ဖန်တီးပေးခြင်း"""
    return f"{st.session_state.sid}_{filename}"

# --- Page Configuration ---
st.set_page_config(page_title="Pro Recap Auto (20 Min+ Ready)", page_icon="🎬", layout="wide")

st.markdown("""
    <style>
    .main-title { font-size: 32px; font-weight: 800; color: #00E676; text-align: center; margin-bottom: 5px; }
    .sub-title { text-align: center; color: #A0A0A0; font-size: 14px; margin-bottom: 30px; font-family: monospace;}
    .step-header { color: #00E676; font-weight: bold; font-size: 20px; border-bottom: 1px solid #00E676; padding-bottom: 10px; margin-bottom: 20px; }
    .stButton>button { background-color: #00E676; color: #111111; font-weight: bold; border-radius: 8px; width: 100%; transition: 0.3s; }
    .stButton>button:hover { background-color: #B2FF59; color: #000000; }
    </style>
""", unsafe_allow_html=True)

# --- Session States ---
if 'step' not in st.session_state: st.session_state.step = 1
for k in ["draft_script", "ready_made_prompt", "video_duration", "final_script", "thumb_prompt"]:
    if k not in st.session_state: st.session_state[k] = ""
if 'is_rendered' not in st.session_state: st.session_state.is_rendered = False
for k in ["gemini_1", "gemini_2", "gemini_3", "groq_1"]:
    if k not in st.session_state: st.session_state[k] = ""

def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1

def reset_project():
    gc.collect()
    for f in [fpath(x) for x in ["temp_video.mp4", "temp_audio.mp3", "final_voice.mp3", "final_merged.mp4", "subtitles.srt", "assets.zip"]]:
        if os.path.exists(f): os.remove(f)
    st.session_state.step = 1
    st.session_state.is_rendered = False
    st.rerun()

# --- FFmpeg Helpers ---
def get_duration(filename):
    """ဗီဒီယို သို့မဟုတ် အသံဖိုင်၏ အရှည် (စက္ကန့်) ကို ffprobe ဖြင့် တိကျစွာ ယူခြင်း"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    return float(result.stdout)

# --- AI Executors ---
async def generate_premium_voice_and_srt(text, voice_name, audio_filename, srt_filename):
    communicate = edge_tts.Communicate(text, voice_name)
    submaker = edge_tts.SubMaker()
    with open(audio_filename, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                if hasattr(submaker, 'feed'): submaker.feed(chunk)
                else: submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])
    with open(srt_filename, "w", encoding="utf-8") as file:
        if hasattr(submaker, 'get_srt'): file.write(submaker.get_srt())
        else: file.write(submaker.generate_subs())

def execute_gemini_smart(audio_path, tone, duration):
    active_keys = [st.session_state[k] for k in ["gemini_1", "gemini_2", "gemini_3"] if st.session_state[k].strip()]
    if not active_keys: raise Exception("Gemini API Key လိုအပ်ပါသည်။")
    word_limit = int((duration / 60) * 140)
    prompt = f"Act as a professional Burmese movie recapper. Summarize this plot into a natural, engaging Burmese script. TONE: {tone}. LENGTH: ~{word_limit} Burmese words. CRITICAL: Return the final Burmese script ONLY inside a markdown code block (```). Do NOT include English names in parentheses. Write names naturally in Burmese only."
    
    for idx, key in enumerate(active_keys):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            audio_file = genai.upload_file(path=audio_path)
            return model.generate_content([prompt, audio_file]).text
        except Exception as e:
            if "429" in str(e) and idx < len(active_keys) - 1: continue
            else: raise e

def generate_thumbnail_prompt(script):
    key = st.session_state.gemini_1 or st.session_state.gemini_2 or st.session_state.gemini_3
    if not key: return "No Gemini API key available for Thumbnail Prompt."
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"Based on this movie recap script, write a highly descriptive Midjourney/AI image generation prompt (in English) to create an engaging, clickbait YouTube thumbnail. Keep it under 50 words. Focus on main character action, cinematic lighting, and intense emotion.\n\nScript: {script[:1000]}..."
        return model.generate_content(prompt).text.strip()
    except:
        return "Error generating thumbnail prompt."

# --- UI Header ---
st.markdown('<div class="main-title">🎬 Recap Pro (Long-form Edition)</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Blur Subs | Custom Logo | 20-Min Ready FFmpeg Engine</div>', unsafe_allow_html=True)

# ==========================================
# WIZARD STEP 1: Settings & Media
# ==========================================
if st.session_state.step == 1:
    st.markdown('<div class="step-header">Step 1: Setup & Media</div>', unsafe_allow_html=True)
    
    with st.expander("⚙️ API Keys (သင်၏ Key များကို ထည့်ပါ)", expanded=True):
        st.info("💡 App ပိတ်လိုက်သည်နှင့် Key များ ပျက်သွားမည်ဖြစ်၍ လုံခြုံပါသည်။")
        col_g1, col_g2, col_g3 = st.columns(3)
        st.session_state.gemini_1 = col_g1.text_input("Gemini 1", type="password", value=st.session_state.gemini_1)
        st.session_state.gemini_2 = col_g2.text_input("Gemini 2", type="password", value=st.session_state.gemini_2)
        st.session_state.gemini_3 = col_g3.text_input("Gemini 3", type="password", value=st.session_state.gemini_3)
        st.session_state.groq_1 = st.text_input("Groq Key", type="password", value=st.session_state.groq_1)

    input_method = st.radio("Media Source:", ["Upload Video", "YouTube Link"], horizontal=True)
    if input_method == "Upload Video":
        uploaded_file = st.file_uploader("ဗီဒီယိုဖိုင် ရွေးပါ", type=["mp4", "mov"])
        if uploaded_file:
            with open(fpath("temp_video.mp4"), "wb") as f: f.write(uploaded_file.getbuffer())
            st.success("Video Ready!")
    else:
        youtube_url = st.text_input("YouTube Link")
        if st.button("⬇️ Download"):
            with st.spinner("Downloading..."):
                try:
                    with yt_dlp.YoutubeDL({'format': 'best[height<=720]', 'outtmpl': fpath("temp_video.mp4"), 'quiet': True}) as ydl: ydl.download([youtube_url])
                    st.success("Download Complete!")
                except Exception as e: st.error(f"Error: {e}")

    st.markdown("### 🎛️ Preferences")
    col_w, col_t = st.columns(2)
    with col_w:
        workflow = st.radio("🔄 လုပ်ငန်းစဉ်", ["Auto (Gemini)", "Manual (Groq)"])
        script_tone = st.selectbox("📝 Tone", ["Narrative", "Calm", "Energetic", "Dramatic"])
    with col_t:
        tts_engine = st.selectbox("🎙️ Engine", ["Premium (TTS)", "Standard (gTTS)"])
        gender = st.selectbox("👤 Gender", ["Male", "Female"])

    if st.button("🚀 Analyze & Generate Script"):
        if not os.path.exists(fpath("temp_video.mp4")): st.error("⚠️ ဗီဒီယို အရင်တင်ပါ။")
        else:
            with st.spinner("Audio ခွဲထုတ်နေပါသည် (Low Bitrate Optimization)..."):
                st.session_state.video_duration = get_duration(fpath("temp_video.mp4"))
                # Groq API limit မထိစေရန် 64kbps ဖြင့် အသံဖိုင် သေးသေးလေး ထုတ်ယူခြင်း (မိနစ် ၂၀ = ~9MB သာရှိမည်)
                subprocess.run(['ffmpeg', '-y', '-i', fpath("temp_video.mp4"), '-vn', '-ar', '16000', '-ac', '1', '-b:a', '64k', fpath("temp_audio.mp3")], check=True)
                
                tone_map = {"Narrative": "storytelling", "Calm": "calm", "Energetic": "energetic", "Dramatic": "dramatic"}
                try:
                    if "Auto" in workflow:
                        with st.spinner("Gemini ဖြင့် ဇာတ်ညွှန်းရေးနေပါသည်..."):
                            st.session_state.draft_script = execute_gemini_smart(fpath("temp_audio.mp3"), tone_map[script_tone], st.session_state.video_duration)
                        st.session_state.workflow_mode = "Auto"
                    else:
                        with st.spinner("Groq ဖြင့် Transcription လုပ်နေပါသည်..."):
                            client = Groq(api_key=st.session_state.groq_1)
                            with open(fpath("temp_audio.mp3"), "rb") as f:
                                transcription = client.audio.transcriptions.create(file=(fpath("temp_audio.mp3"), f.read()), model="whisper-large-v3", response_format="text")
                            limit = int((st.session_state.video_duration/60)*140)
                            st.session_state.ready_made_prompt = f"Act as a professional movie recapper. Summarize this transcription into a natural Burmese storytelling script. TONE: {tone_map[script_tone]}. LENGTH: ~{limit} words. Return the final Burmese script ONLY inside a markdown code block (
```).\n\nTranscription:\n{transcription}"
                        st.session_state.workflow_mode = "Manual"
                    
                    st.session_state.tts_engine, st.session_state.gender = tts_engine, gender
                    st.session_state.step = 2
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")

# ==========================================
# WIZARD STEP 2: Editor & AI Prompts
# ==========================================
elif st.session_state.step == 2:
    st.markdown('<div class="step-header">Step 2: Script Editor & AI Magic</div>', unsafe_allow_html=True)
    bt = "`" * 3 
    
    if st.session_state.workflow_mode == "Auto":
        display_text = st.session_state.draft_script.replace(f"{bt}text", "").replace(f"{bt}markdown", "").replace(bt, "").strip()
        edited_script = st.text_area("✍️ လိုအပ်ပါက ပြင်ဆင်ပါ (ဇာတ်ညွှန်း):", value=display_text, height=300)
    else:
        st.info("💡 အောက်ပါစာသားကို Copy ယူပြီး Gemini တွင် ထည့်ပါ။ ရလဒ်ကို အောက်တွင် Paste လုပ်ပါ။")
        st.code(st.session_state.ready_made_prompt, language="text")
        edited_script = st.text_area("✍️ Paste translated script here:", value=st.session_state.draft_script, height=300)

    if st.button("🎨 AI Thumbnail Prompt ထုတ်ရန် (Optional)"):
        with st.spinner("Midjourney/Gemini အတွက် Prompt စဉ်းစားပေးနေပါသည်..."):
            st.session_state.thumb_prompt = generate_thumbnail_prompt(edited_script)
            
    if st.session_state.thumb_prompt:
        st.success("🖼️ Image AI တွင် အသုံးပြုရန် Thumbnail Prompt:")
        st.code(st.session_state.thumb_prompt, language="text")

    c1, c2 = st.columns(2)
    if c1.button("⬅️ Back"): st.session_state.step = 1; st.rerun()
    if c2.button("🎙️ Next: Render Pro Video"):
        if not edited_script.strip(): st.error("စာသားထည့်ပါ")
        else: 
            clean_edited = edited_script.replace(f"{bt}text", "").replace(f"{bt}markdown", "").replace(bt, "").strip()
            st.session_state.final_script = clean_edited
            st.session_state.is_rendered = False 
            next_step()
            st.rerun()

# ==========================================
# WIZARD STEP 3: Rendering (FFMPEG Engine)
# ==========================================
elif st.session_state.step == 3:
    st.markdown('<div class="step-header">Step 3: Final Output (High-Performance Engine)</div>', unsafe_allow_html=True)
    
    if not st.session_state.is_rendered:
        try:
            with st.spinner("🎙️ အသံနှင့် စာတန်းထိုး ဖန်တီးနေသည်..."):
                if "Premium" in st.session_state.tts_engine:
                    voice = "my-MM-ThihaNeural" if st.session_state.gender == "Male" else "my-MM-NilarNeural"
                    asyncio.run(generate_premium_voice_and_srt(st.session_state.final_script, voice, fpath("final_voice.mp3"), fpath("subtitles.srt")))
                else: 
                    gTTS(text=st.session_state.final_script, lang='my').save(fpath("final_voice.mp3"))
            
            with st.spinner("🎬 ဗီဒီယို ပေါင်းစပ်နေသည် (FFmpeg Blur, Logo & Hardsub)... ဤအဆင့်သည် မိနစ်အနည်းငယ် ကြာနိုင်ပါသည်။"):
                v_dur = get_duration(fpath("temp_video.mp4"))
                a_dur = get_duration(fpath("final_voice.mp3"))
                speed_factor = v_dur / a_dur  # Audio အရှည်နှင့် ကိုက်ညီရန် Video ကို အမြန်/အနှေး ချိန်မည်
                
                # လိုအပ်သော Paths များ
                v_in = fpath("temp_video.mp4")
                a_in = fpath("final_voice.mp3")
                sub_in = fpath("subtitles.srt")
                v_out = fpath("final_merged.mp4")
                
                # Filter Graph တည်ဆောက်ခြင်း (Speed -> Scale -> Split -> Blur Bottom -> Overlay -> Logo -> Subtitles)
                filter_complex = f"[0:v]setpts={speed_factor}*PTS[v_speed];"
                filter_complex += "[v_speed]scale=w=trunc(iw/2)*2:h=trunc(ih/2)*2[v_norm];" # ဘေးကင်းရန် scale ချခြင်း
                filter_complex += "[v_norm]split=2[orig][bot];"
                filter_complex += "[bot]crop=iw:ih*0.2:0:ih*0.8,boxblur=20:20[blur];" # အောက်ခြေ ၂၀% ကို ဝါးခြင်း
                filter_complex += "[orig][blur]overlay=0:H*0.8[v_blur];"
                
                # လိုဂို ထည့်သွင်းခြင်း (logo.png ရှိမှသာ)
                if os.path.exists("logo.png"):
                    filter_complex += "[v_blur][2:v]overlay=W-w-20:20[v_logo];" # ညာဘက်အပေါ်ထောင့်
                    filter_complex += f"[v_logo]subtitles={sub_in}[v_final]"
                    cmd = [
                        "ffmpeg", "-y", "-i", v_in, "-i", a_in, "-i", "logo.png",
                        "-filter_complex", filter_complex,
                        "-map", "[v_final]", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k", v_out
                    ]
                else:
                    filter_complex += f"[v_blur]subtitles={sub_in}[v_final]"
                    cmd = [
                        "ffmpeg", "-y", "-i", v_in, "-i", a_in,
                        "-filter_complex", filter_complex,
                        "-map", "[v_final]", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k", v_out
                    ]
                
                subprocess.run(cmd, check=True)
                
            with st.spinner("📦 Raw Assets များကို Zip တွဲနေပါသည်..."):
                with zipfile.ZipFile(fpath("assets.zip"), 'w') as zipf:
                    zipf.write(fpath("final_voice.mp3"), "Voice_Track.mp3")
                    if os.path.exists(fpath("subtitles.srt")):
                        zipf.write(fpath("subtitles.srt"), "Subtitles.srt")
            
            st.session_state.is_rendered = True 
            st.rerun() 
        except Exception as e: 
            st.error(f"Error: {e}")

    if st.session_state.is_rendered:
        st.success("🎉 ပြီးပါပြီ! Video အဆင်သင့်ဖြစ်ပါပြီ။")
        
        if os.path.exists(fpath("final_merged.mp4")): 
            st.video(fpath("final_merged.mp4"))
        
        st.markdown("### 📥 ဒေါင်းလုဒ် ရယူရန်")
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            if os.path.exists(fpath("final_merged.mp4")):
                with open(fpath("final_merged.mp4"), "rb") as f: 
                    st.download_button("🎬 Final Video", data=f, file_name="Final_Recap_Pro.mp4")
        with col_d2:
            if os.path.exists(fpath("subtitles.srt")):
                with open(fpath("subtitles.srt"), "r", encoding="utf-8") as f: 
                    st.download_button("📝 SRT စာတန်းထိုးဖိုင်", data=f.read(), file_name="Subtitles.srt", mime="text/srt")
        with col_d3:
            if os.path.exists(fpath("assets.zip")):
                with open(fpath("assets.zip"), "rb") as f: 
                    st.download_button("📦 အသံနှင့် စာတန်းထိုး (Zip)", data=f, file_name="Raw_Assets.zip", mime="application/zip")
                
        st.markdown("---")
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("⬅️ Back to Editor (စာသားပြန်ပြင်ရန်)"): 
                st.session_state.step = 2
                st.session_state.is_rendered = False
                st.rerun()
        with col_b2:
            if st.button("🔄 New Project (အသစ်ပြန်စရန်)"): reset_project()
