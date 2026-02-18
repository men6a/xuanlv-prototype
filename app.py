import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
import time
from music21 import converter, note, stream, midi

# 尝试导入自动刷新组件，若未安装则提示
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st.error("请先安装 streamlit-autorefresh：`pip install streamlit-autorefresh`")
    st.stop()

st.set_page_config(page_title="玄·律标注原型", layout="wide")

# 自定义标题样式（与普通文本大小一致）
st.markdown("""
<style>
.main-title {
    font-size: 1.5rem;
    font-weight: bold;
    margin-bottom: 1rem;
}
</style>
<div class="main-title">🎵 玄·律标注原型</div>
""", unsafe_allow_html=True)

st.markdown("上传MIDI文件，生成变体，直接点击播放器试听（内置音源）。")

# 初始化session_state
if 'variants' not in st.session_state:
    st.session_state.variants = []
if 'variant_meta' not in st.session_state:
    st.session_state.variant_meta = []
if 'labels_surprise' not in st.session_state:
    st.session_state.labels_surprise = []
if 'labels_beauty' not in st.session_state:
    st.session_state.labels_beauty = []
if 'labels_feelings' not in st.session_state:
    st.session_state.labels_feelings = []

# 记录每个变体的最后修改时间和已保存的值，用于自动保存
if 'last_modified' not in st.session_state:
    st.session_state.last_modified = []          # 时间戳列表
if 'last_saved_surprise' not in st.session_state:
    st.session_state.last_saved_surprise = []
if 'last_saved_beauty' not in st.session_state:
    st.session_state.last_saved_beauty = []
if 'last_saved_feelings' not in st.session_state:
    st.session_state.last_saved_feelings = []

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
        if random.random() < 0.7:
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
        else:
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

def get_midi_player_html(midi_bytes, player_id):
    """
    返回一个仅包含播放条的 HTML 片段，背景透明（由父容器提供奶绿色），
    按钮和进度条使用深绿色，无任何边框、阴影或多余线条。
    """
    import base64
    midi_base64 = base64.b64encode(midi_bytes).decode('utf-8')
    data_url = f"data:audio/midi;base64,{midi_base64}"

    html = f"""
    <div style="margin:0; padding:0; background:transparent; line-height:0;">
        <script src="https://cdn.jsdelivr.net/combine/npm/tone@14.7.58,npm/@magenta/music@1.23.1/es6/core.js,npm/focus-visible@5,npm/html-midi-player@1.5.0"></script>
        <midi-player
            id="player-{player_id}"
            src="{data_url}"
            sound-font
            style="
                width:100%;
                margin:0;
                padding:0;
                display:block;
                background: transparent;
                border: none;
                box-shadow: none;
                outline: none;
                --midi-player-background: transparent;
                --midi-player-progress-background: transparent;
                --midi-player-button-color: #2d4a1e;
                --midi-player-progress-color: #2d4a1e;
                --midi-player-handle-color: #2d4a1e;
            ">
        </midi-player>
    </div>
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
            new_variants = []
            new_meta = []
            for mel in raw_melodies:
                for i in range(n_per_original):
                    strength = random.uniform(0.2, 0.8)
                    var = generate_variant(mel, strength)
                    new_variants.append(var)
                    new_meta.append({
                        'original_idx': len(raw_melodies)-1,
                        'surprise_strength': strength
                    })
            st.session_state.variants = new_variants
            st.session_state.variant_meta = new_meta
            st.session_state.labels_surprise = [None] * len(new_variants)
            st.session_state.labels_beauty = [None] * len(new_variants)
            st.session_state.labels_feelings = [""] * len(new_variants)
            # 初始化自动保存相关列表
            current_time = time.time()
            st.session_state.last_modified = [current_time] * len(new_variants)
            st.session_state.last_saved_surprise = [None] * len(new_variants)
            st.session_state.last_saved_beauty = [None] * len(new_variants)
            st.session_state.last_saved_feelings = [""] * len(new_variants)
            st.success(f"已生成 {len(new_variants)} 个变体")

# 主界面：标注（默认展开）
st.header("3. 标注变体")

# 自动刷新（每3秒一次，用于自动保存）
if st.session_state.variants:
    refresh_count = st_autorefresh(interval=3000, key="auto_save_refresh")

if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):  # 只显示前10个
        with st.expander(f"变体 #{idx}", expanded=True):
            left_col, right_col = st.columns(2)
            
            with left_col:
                midi_bytes = get_midi_bytes(var)
                
                # 统一的奶绿色背景容器（上内边距0使播放条贴顶）
                st.markdown(
                    """
                    <style>
                    .mint-container {
                        background-color: #e6f3da;
                        padding: 0 12px 12px 12px;
                        border-radius: 8px;
                        margin-bottom: 8px;
                    }
                    .mint-container .stTextArea textarea {
                        background-color: #f8fff0;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )
                
                st.markdown('<div class="mint-container">', unsafe_allow_html=True)
                
                # 播放器（背景透明，由容器提供奶绿色）
                player_html = get_midi_player_html(midi_bytes, idx)
                st.components.v1.html(player_html, height=50)
                
                # 感受词输入框
                if idx < len(st.session_state.labels_feelings):
                    current_f = st.session_state.labels_feelings[idx] if st.session_state.labels_feelings[idx] is not None else ""
                else:
                    current_f = ""
                
                new_f = st.text_area(
                    "感受词（可输入多个词，逗号分隔）",
                    value=current_f,
                    height=80,
                    placeholder="例如：跳跃、不协和、温柔...",
                    key=f"f_{idx}",
                    label_visibility="collapsed"
                )
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # 下载按钮放在容器外
                st.download_button(
                    "⬇️ 下载MIDI文件",
                    data=midi_bytes,
                    file_name=f"variant_{idx}.mid",
                    mime="audio/midi",
                    key=f"download_{idx}"
                )
            
            with right_col:
                st.markdown("#### 标注")
                # 确保索引有效
                if idx < len(st.session_state.labels_surprise):
                    current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                else:
                    current_s = 0.5
                if idx < len(st.session_state.labels_beauty):
                    current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                else:
                    current_b = 0.5
                
                new_s = st.slider("意外度", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度", 0.0, 1.0, current_b, key=f"b_{idx}")
                
                # 手动保存按钮
                if st.button("保存标注", key=f"save_{idx}"):
                    # 确保列表足够长
                    while len(st.session_state.labels_surprise) <= idx:
                        st.session_state.labels_surprise.append(None)
                    while len(st.session_state.labels_beauty) <= idx:
                        st.session_state.labels_beauty.append(None)
                    while len(st.session_state.labels_feelings) <= idx:
                        st.session_state.labels_feelings.append("")
                    
                    st.session_state.labels_surprise[idx] = new_s
                    st.session_state.labels_beauty[idx] = new_b
                    st.session_state.labels_feelings[idx] = new_f
                    # 更新最后保存的值
                    st.session_state.last_saved_surprise[idx] = new_s
                    st.session_state.last_saved_beauty[idx] = new_b
                    st.session_state.last_saved_feelings[idx] = new_f
                    st.success("✅ 已手动保存")
                
                # 自动保存逻辑：每次刷新时检查是否需要保存
                # 获取当前值
                current_s_val = st.session_state.get(f"s_{idx}", 0.5)
                current_b_val = st.session_state.get(f"b_{idx}", 0.5)
                current_f_val = st.session_state.get(f"f_{idx}", "")
                
                # 检查是否与最后保存的值不同
                last_s = st.session_state.last_saved_surprise[idx] if idx < len(st.session_state.last_saved_surprise) else None
                last_b = st.session_state.last_saved_beauty[idx] if idx < len(st.session_state.last_saved_beauty) else None
                last_f = st.session_state.last_saved_feelings[idx] if idx < len(st.session_state.last_saved_feelings) else ""
                
                changed = (current_s_val != last_s) or (current_b_val != last_b) or (current_f_val != last_f)
                
                if changed:
                    # 更新时间戳（每次刷新都会更新，但保存逻辑在下方统一执行）
                    st.session_state.last_modified[idx] = time.time()
    
    # 在每次刷新时执行自动保存检查
    current_time = time.time()
    for idx in range(len(st.session_state.variants[:10])):
        if idx < len(st.session_state.last_modified):
            time_diff = current_time - st.session_state.last_modified[idx]
            # 如果超过3秒且数据有变化
            if time_diff >= 3:
                # 获取当前值
                current_s_val = st.session_state.get(f"s_{idx}", 0.5)
                current_b_val = st.session_state.get(f"b_{idx}", 0.5)
                current_f_val = st.session_state.get(f"f_{idx}", "")
                
                # 获取最后保存的值
                last_s = st.session_state.last_saved_surprise[idx] if idx < len(st.session_state.last_saved_surprise) else None
                last_b = st.session_state.last_saved_beauty[idx] if idx < len(st.session_state.last_saved_beauty) else None
                last_f = st.session_state.last_saved_feelings[idx] if idx < len(st.session_state.last_saved_feelings) else ""
                
                changed = (current_s_val != last_s) or (current_b_val != last_b) or (current_f_val != last_f)
                
                if changed:
                    # 保存到正式列表
                    while len(st.session_state.labels_surprise) <= idx:
                        st.session_state.labels_surprise.append(None)
                    while len(st.session_state.labels_beauty) <= idx:
                        st.session_state.labels_beauty.append(None)
                    while len(st.session_state.labels_feelings) <= idx:
                        st.session_state.labels_feelings.append("")
                    
                    st.session_state.labels_surprise[idx] = current_s_val
                    st.session_state.labels_beauty[idx] = current_b_val
                    st.session_state.labels_feelings[idx] = current_f_val
                    
                    # 更新最后保存的值
                    while len(st.session_state.last_saved_surprise) <= idx:
                        st.session_state.last_saved_surprise.append(None)
                    while len(st.session_state.last_saved_beauty) <= idx:
                        st.session_state.last_saved_beauty.append(None)
                    while len(st.session_state.last_saved_feelings) <= idx:
                        st.session_state.last_saved_feelings.append("")
                    
                    st.session_state.last_saved_surprise[idx] = current_s_val
                    st.session_state.last_saved_beauty[idx] = current_b_val
                    st.session_state.last_saved_feelings[idx] = current_f_val
                    
                    # 静默保存，不显示提示
                    # 可取消下面注释以显示短暂提示
                    # st.toast(f"变体 #{idx} 已自动保存", icon="💾")
else:
    st.info("请在左侧上传MIDI文件并生成变体")
