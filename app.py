import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
from music21 import converter, note, stream, midi

st.set_page_config(page_title="玄·律标注原型", layout="wide")
st.title("🎵 玄·律标注原型 (网页直接播放版)")
st.markdown("上传MIDI文件，生成变体，直接点击播放试听，并标注。")

# 初始化session_state
if 'variants' not in st.session_state:
    st.session_state.variants = []
if 'variant_meta' not in st.session_state:
    st.session_state.variant_meta = []
if 'labels_surprise' not in st.session_state:
    st.session_state.labels_surprise = []
if 'labels_beauty' not in st.session_state:
    st.session_state.labels_beauty = []
if 'current_midi_base64' not in st.session_state:
    st.session_state.current_midi_base64 = None

# ---------- 生成变体函数（增强音乐性）----------
def generate_variant(melody_stream, surprise_strength=0.3):
    C_MAJOR = {0, 2, 4, 5, 7, 9, 11}
    COMMON_DURS = [0.5, 1, 2]
    original_notes = list(melody_stream.getElementsByClass(note.Note))
    if not original_notes:
        return stream.Stream()
    new_notes = [copy.deepcopy(n) for n in original_notes]
    n_changes = max(1, int(len(new_notes) * surprise_strength))
    for _ in range(n_changes):
        idx = random.randint(0, len(new_notes)-1)
        current = new_notes[idx]
        current_pitch = current.pitch.midi
        current_dur = current.quarterLength
        if random.random() < 0.7:  # 改音高
            attempts = 0
            new_pitch = None
            while attempts < 10:
                step = random.choice([-2, -1, 1, 2]) if surprise_strength > 0.5 else random.choice([-1, 1])
                candidate = current_pitch + step
                if (candidate % 12) in C_MAJOR and 0 <= candidate <= 127:
                    prev_pitch = new_notes[idx-1].pitch.midi if idx > 0 else candidate
                    next_pitch = new_notes[idx+1].pitch.midi if idx < len(new_notes)-1 else candidate
                    if abs(candidate - prev_pitch) <= 7 and abs(candidate - next_pitch) <= 7:
                        new_pitch = candidate
                        break
                attempts += 1
            if new_pitch is not None:
                current.pitch.midi = new_pitch
        else:  # 改节奏
            if current_dur in COMMON_DURS:
                new_dur = random.choice([d for d in COMMON_DURS if d != current_dur])
                current.quarterLength = new_dur
        if surprise_strength > 0.8 and random.random() < 0.3:
            leap = random.choice([-7, 7])
            candidate = current_pitch + leap
            if (candidate % 12) in C_MAJOR and 0 <= candidate <= 127:
                current.pitch.midi = candidate
    new_stream = stream.Stream()
    for n in new_notes:
        new_stream.append(n)
    return new_stream
# ---------------------------------------------

def get_midi_bytes(melody_stream):
    """将music21流转换为MIDI文件字节数据"""
    temp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
    mf = midi.translate.music21ObjectToMidiFile(melody_stream)
    mf.open(temp.name, 'wb')
    mf.write()
    mf.close()
    with open(temp.name, 'rb') as f:
        data = f.read()
    import os
    os.unlink(temp.name)
    return data

def midi_to_base64(midi_bytes):
    """将MIDI字节转换为Base64字符串，用于嵌入HTML"""
    return base64.b64encode(midi_bytes).decode('utf-8')

def get_midi_player_html(midi_base64):
    """返回一个嵌入MidiPlayerJS的HTML字符串，用于播放Base64编码的MIDI"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/midijs@2.0.0/dist/MidiPlayer.min.js"></script>
    </head>
    <body>
        <div id="player"></div>
        <button onclick="playMidi()">▶️ 在页面中播放</button>
        <script>
            function playMidi() {{
                // 将Base64解码为二进制
                var binary = atob("{midi_base64}");
                var array = new Uint8Array(binary.length);
                for (var i = 0; i < binary.length; i++) {{
                    array[i] = binary.charCodeAt(i);
                }}
                // 创建Blob并生成URL
                var blob = new Blob([array], {{ type: 'audio/midi' }});
                var url = URL.createObjectURL(blob);
                // 使用MidiPlayer播放
                var player = new MidiPlayer.Player(function(event) {{}});
                player.loadFile(url, function() {{
                    player.play();
                }});
            }}
        </script>
    </body>
    </html>
    """
    return html

# 侧边栏：上传MIDI
with st.sidebar:
    st.header("1. 导入MIDI文件")
    uploaded_files = st.file_uploader("选择MIDI文件", type=['mid','midi'], accept_multiple_files=True)

    raw_melodies = []
    if uploaded_files:
        for f in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            try:
                score = converter.parse(tmp_path)
                note_list = list(score.parts[0].flat.getElementsByClass(note.Note))
                if note_list:
                    melody_stream = stream.Stream(note_list)
                    raw_melodies.append(melody_stream)
                    st.success(f"已导入: {f.name}")
                else:
                    st.warning(f"无音符: {f.name}")
            except Exception as e:
                st.error(f"解析失败: {f.name} - {str(e)}")
            import os
            os.unlink(tmp_path)

    st.header("2. 生成变体")
    n_per_original = st.number_input("每首生成变体数", min_value=1, max_value=10, value=3)
    if st.button("生成变体"):
        if not raw_melodies:
            st.warning("请先导入MIDI")
        else:
            st.session_state.variants = []
            st.session_state.variant_meta = []
            for mel in raw_melodies:
                for i in range(n_per_original):
                    strength = random.uniform(0.2, 0.8)
                    var = generate_variant(mel, strength)
                    st.session_state.variants.append(var)
                    st.session_state.variant_meta.append({
                        'original_idx': len(raw_melodies)-1,
                        'surprise_strength': strength
                    })
            st.session_state.labels_surprise = [None] * len(st.session_state.variants)
            st.session_state.labels_beauty = [None] * len(st.session_state.variants)
            st.success(f"已生成 {len(st.session_state.variants)} 个变体")

# 主界面：标注
st.header("3. 标注变体")

# 创建一个占位符用于动态显示MIDI播放器
player_placeholder = st.empty()

if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):  # 只显示前10个
        with st.expander(f"变体 #{idx}"):
            col1, col2 = st.columns([1,2])
            with col1:
                midi_bytes = get_midi_bytes(var)
                midi_b64 = midi_to_base64(midi_bytes)
                if st.button(f"▶️ 网页播放变体 #{idx}", key=f"play_{idx}"):
                    st.session_state.current_midi_base64 = midi_b64
                    st.rerun()  # 重新运行以显示播放器
                st.download_button(
                    "⬇️ 下载MIDI文件",
                    data=midi_bytes,
                    file_name=f"variant_{idx}.mid",
                    mime="audio/midi",
                    key=f"download_{idx}"
                )
            with col2:
                current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                new_s = st.slider("意外度", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度", 0.0, 1.0, current_b, key=f"b_{idx}")
                if st.button("保存标注", key=f"save_{idx}"):
                    st.session_state.labels_surprise[idx] = new_s
                    st.session_state.labels_beauty[idx] = new_b
                    st.success("已保存")

    # 如果当前有要播放的MIDI，在占位符中显示播放器
    if st.session_state.current_midi_base64:
        player_placeholder.markdown("### 🎧 当前播放")
        player_html = get_midi_player_html(st.session_state.current_midi_base64)
        st.components.v1.html(player_html, height=100)
        if st.button("关闭播放器"):
            st.session_state.current_midi_base64 = None
            st.rerun()
else:
    st.info("请在左侧上传MIDI文件并生成变体")
