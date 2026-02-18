import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
from music21 import converter, note, stream, midi

st.set_page_config(page_title="玄·律标注原型", layout="wide")
st.title("🎵 玄·律标注原型 (网页部署版)")
st.markdown("上传MIDI文件，生成变体，标注意外度和好听度。")

# 初始化session_state
if 'variants' not in st.session_state:
    st.session_state.variants = []
if 'variant_meta' not in st.session_state:
    st.session_state.variant_meta = []
if 'labels_surprise' not in st.session_state:
    st.session_state.labels_surprise = []
if 'labels_beauty' not in st.session_state:
    st.session_state.labels_beauty = []

# 特征提取函数
def extract_features(melody_stream):
    pitches = []
    durations = []
    for n in melody_stream.flat.notes:
        if isinstance(n, note.Note):
            pitches.append(n.pitch.midi % 12)
            durations.append(n.quarterLength)
    if len(pitches) == 0:
        return None
    hist, _ = np.histogram(pitches, bins=np.arange(13), density=True)
    intervals = np.diff(pitches)
    up = np.sum(intervals > 0) / max(len(intervals),1)
    down = np.sum(intervals < 0) / max(len(intervals),1)
    same = np.sum(intervals == 0) / max(len(intervals),1)
    avg_dur = np.mean(durations) if durations else 0
    features = np.concatenate([hist, [up, down, same, avg_dur]])
    return features

# 变体生成函数
def generate_variant(melody_stream, surprise_strength=0.3):
    new_stream = melody_stream.flat.copy()
    notes = list(new_stream.notes)
    if not notes:
        return new_stream
    n_changes = max(1, int(len(notes) * surprise_strength))
    for _ in range(n_changes):
        idx = random.randint(0, len(notes)-1)
        if isinstance(notes[idx], note.Note):
            delta = random.choice([-2, -1, 1, 2])
            new_pitch = notes[idx].pitch.midi + delta
            if 0 <= new_pitch <= 127:
                notes[idx].pitch.midi = new_pitch
            if random.random() < 0.3:
                notes[idx].quarterLength *= random.choice([0.5, 1, 2])
    new_stream = stream.Stream()
    for n in notes:
        new_stream.append(n)
    return new_stream

# 生成MIDI下载数据
def get_midi_data(melody_stream):
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
                melody = score.parts[0].flat.getElementsByClass(note.Note)
                if len(melody) > 0:
                    raw_melodies.append(melody)
                    st.success(f"已导入: {f.name}")
                else:
                    st.warning(f"无音符: {f.name}")
            except:
                st.error(f"解析失败: {f.name}")
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
if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):  # 只显示前10个
        with st.expander(f"变体 #{idx}"):
            col1, col2 = st.columns([1,2])
            with col1:
                midi_bytes = get_midi_data(var)
                st.download_button("⬇️ 下载MIDI试听", data=midi_bytes, file_name=f"variant_{idx}.mid", mime="audio/midi")
            with col2:
                current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                new_s = st.slider("意外度", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度", 0.0, 1.0, current_b, key=f"b_{idx}")
                if st.button("保存标注", key=f"save_{idx}"):
                    st.session_state.labels_surprise[idx] = new_s
                    st.session_state.labels_beauty[idx] = new_b
                    st.success("已保存")
else:

    st.info("请在左侧上传MIDI文件并生成变体")
