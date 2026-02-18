import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
from music21 import converter, note, stream, midi
from collections import Counter

st.set_page_config(page_title="玄·律标注原型", layout="wide")

# 隐藏页面加载遮罩
st.markdown("""
<style>
.stApp::before {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# 全局字体调小
st.markdown("""
<style>
html, body, [class*="css"]  {
    font-size: 0.9rem;
}
.main-title {
    font-size: 1.4rem;
    font-weight: bold;
    margin-bottom: 1rem;
}
.stSlider label {
    font-size: 0.9rem !important;
}
/* 按钮极限贴近感受输入框 */
.button-row {
    margin-top: -18px !important;
}
.button-row .stButton button, .button-row .stDownloadButton button {
    font-size: 0.8rem !important;
    padding: 0.15rem 0.4rem !important;
    line-height: 1.2;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🎵 玄·律标注原型</div>', unsafe_allow_html=True)
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
if 'save_indicator' not in st.session_state:
    st.session_state.save_indicator = []

# ---------- 增强版生成变体函数（融合多维度音乐理论）----------
def generate_variant(melody_stream, surprise_strength=0.3,
                     key='C', mode='major', style='classical'):
    """
    融合多维度音乐规则的旋律变体生成
    参数:
        melody_stream: music21流对象
        surprise_strength: 0-1, 控制意外程度
        key: 调性 (C, G, D, A, E, F, Bb 等)
        mode: 大调/小调 (major/minor)
        style: 风格偏好 (classical, jazz, folk)
    """
    # 1. 调性与音阶定义（根据key和mode动态计算音阶）
    # 半音阶索引: C=0, C#=1, D=2, D#=3, E=4, F=5, F#=6, G=7, G#=8, A=9, A#=10, B=11
    note_to_index = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 'A#':10, 'Bb':10, 'B':11}
    # 大调音程模式：全全半全全全半 (2,2,1,2,2,2,1)
    major_intervals = [2,2,1,2,2,2,1]
    # 自然小调音程模式：全半全全半全全 (2,1,2,2,1,2,2)
    minor_intervals = [2,1,2,2,1,2,2]

    root_idx = note_to_index.get(key, 0)
    if mode == 'major':
        intervals = major_intervals
    else:
        intervals = minor_intervals

    scale_notes = set()
    current = root_idx
    for interval in intervals:
        scale_notes.add(current % 12)
        current += interval
    # 添加最后一个音（八度重复）
    scale_notes.add(root_idx % 12)

    # 2. 音程概率分布（符合幂律）
    INTERVAL_WEIGHTS = {
        1: 0.35,   # 二度
        2: 0.25,   # 三度
        3: 0.15,   # 四度
        4: 0.10,   # 五度
        5: 0.08,   # 六度
        6: 0.05,   # 七度
        7: 0.02,   # 八度及以上
    }

    # 3. 节奏模式
    COMMON_DURS = [0.5, 1, 2, 3, 4]  # 八分、四分、附点二分、二分、全音符
    RHYTHM_PATTERNS = {
        'classical': [1, 0.5, 0.5, 1, 1, 2],
        'jazz': [0.5, 0.5, 1, 1.5, 0.5, 1],
        'folk': [1, 1, 0.5, 0.5, 1, 2],
    }

    # 4. GTTM边界检测函数
    def is_boundary(notes, idx):
        if idx <= 0 or idx >= len(notes)-1:
            return False
        if notes[idx].quarterLength > 1.5:
            return True
        prev_interval = abs(notes[idx].pitch.midi - notes[idx-1].pitch.midi)
        next_interval = abs(notes[idx+1].pitch.midi - notes[idx].pitch.midi)
        if prev_interval > 5 and next_interval > 5:
            return True
        return False

    # 5. 主生成逻辑
    original_notes = list(melody_stream.getElementsByClass(note.Note))
    if not original_notes:
        return stream.Stream()

    new_notes = [copy.deepcopy(n) for n in original_notes]
    n_changes = max(1, int(len(new_notes) * surprise_strength))

    # 分析原始旋律特征
    original_pitches = [n.pitch.midi for n in original_notes]
    avg_pitch = np.mean(original_pitches) if original_pitches else 60
    pitch_range = max(original_pitches) - min(original_pitches) if original_pitches else 12

    for _ in range(n_changes):
        idx = random.randint(0, len(new_notes)-1)
        current_note = new_notes[idx]
        current_pitch = current_note.pitch.midi
        current_dur = current_note.quarterLength

        modify_type = random.choices(
            ['pitch', 'rhythm', 'both'],
            weights=[0.6, 0.3, 0.1]
        )[0]

        # ----- 音高修改 -----
        if modify_type in ['pitch', 'both']:
            interval_probs = list(INTERVAL_WEIGHTS.values())
            if surprise_strength > 0.7:
                interval_probs = [p * (1 + surprise_strength) for p in interval_probs]
            interval = random.choices(list(INTERVAL_WEIGHTS.keys()), weights=interval_probs)[0]

            if idx > 0:
                prev_pitch = new_notes[idx-1].pitch.midi
                if current_pitch > prev_pitch:
                    dir_weights = {'up': 0.6, 'down': 0.3, 'same': 0.1}
                elif current_pitch < prev_pitch:
                    dir_weights = {'up': 0.3, 'down': 0.6, 'same': 0.1}
                else:
                    dir_weights = {'up': 0.4, 'down': 0.4, 'same': 0.2}
            else:
                dir_weights = {'up': 0.4, 'down': 0.4, 'same': 0.2}

            direction = random.choices(
                list(dir_weights.keys()),
                weights=list(dir_weights.values())
            )[0]

            if direction == 'up':
                candidate = current_pitch + interval
            elif direction == 'down':
                candidate = current_pitch - interval
            else:
                candidate = current_pitch

            # 调性约束：调整到最近的调内音
            if (candidate % 12) not in scale_notes:
                for offset in [1, -1, 2, -2, 3, -3]:
                    test_note = candidate + offset
                    if 0 <= test_note <= 127 and (test_note % 12) in scale_notes:
                        candidate = test_note
                        break

            # 音域约束
            if abs(candidate - avg_pitch) > pitch_range * 1.5:
                candidate = int(avg_pitch + (candidate - avg_pitch) * 0.5)

            if is_boundary(new_notes, idx):
                pass  # 边界处可放宽约束

            if 0 <= candidate <= 127:
                current_note.pitch.midi = candidate

        # ----- 节奏修改 -----
        if modify_type in ['rhythm', 'both']:
            if style in RHYTHM_PATTERNS and random.random() < 0.4:
                pattern = RHYTHM_PATTERNS[style]
                new_dur = random.choice(pattern)
            else:
                new_dur = random.choice([d for d in COMMON_DURS if d != current_dur])
            if new_dur not in COMMON_DURS:
                new_dur = 1.0
            current_note.quarterLength = new_dur

    new_stream = stream.Stream()
    for n in new_notes:
        new_stream.append(n)
    return new_stream
# ---------------------------------------------

def get_midi_bytes(melody_stream):
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

    st.header("2. 选择音乐参数")
    # 调性选择
    key_options = ['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab']
    selected_key = st.selectbox("调性", key_options, index=0)
    # 调式选择
    mode_options = ['major', 'minor']
    selected_mode = st.radio("调式", mode_options, horizontal=True)
    # 风格选择
    style_options = ['classical', 'jazz', 'folk']
    selected_style = st.selectbox("风格", style_options, index=0)

    st.header("3. 生成变体")
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
                    # 使用用户选择的音乐参数
                    var = generate_variant(
                        mel,
                        strength,
                        key=selected_key,
                        mode=selected_mode,
                        style=selected_style
                    )
                    new_variants.append(var)
                    new_meta.append({
                        'original_idx': len(raw_melodies)-1,
                        'surprise_strength': strength,
                        'key': selected_key,
                        'mode': selected_mode,
                        'style': selected_style
                    })
            st.session_state.variants = new_variants
            st.session_state.variant_meta = new_meta
            st.session_state.labels_surprise = [None] * len(new_variants)
            st.session_state.labels_beauty = [None] * len(new_variants)
            st.session_state.labels_feelings = [""] * len(new_variants)
            st.session_state.save_indicator = [""] * len(new_variants)
            st.success(f"已生成 {len(new_variants)} 个变体")

# 主界面：标注（默认展开）
if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):
        indicator = st.session_state.save_indicator[idx] if idx < len(st.session_state.save_indicator) else ""
        # 显示当前变体使用的音乐参数（可选）
        meta = st.session_state.variant_meta[idx] if idx < len(st.session_state.variant_meta) else {}
        param_str = f"{meta.get('key','C')} {meta.get('mode','major')} {meta.get('style','classical')}" if meta else ""
        expander_title = f"变体 #{idx} {indicator}  {param_str}"
        with st.expander(expander_title, expanded=True):
            left_col, right_col = st.columns(2)
            with left_col:
                midi_bytes = get_midi_bytes(var)
                player_html = get_midi_player_html(midi_bytes, idx)
                st.components.v1.html(player_html, height=60)

                if idx < len(st.session_state.labels_feelings):
                    current_f = st.session_state.labels_feelings[idx] if st.session_state.labels_feelings[idx] is not None else ""
                else:
                    current_f = ""
                st.text_area(
                    "感受词",
                    value=current_f,
                    height=80,
                    placeholder="请标注变体听感（例如：跳跃、不协和、温柔...）",
                    key=f"f_{idx}",
                    label_visibility="collapsed"
                )

                # 按钮行
                st.markdown('<div class="button-row">', unsafe_allow_html=True)
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    st.download_button(
                        "⬇️ 下载MIDI文件",
                        data=get_midi_bytes(var),
                        file_name=f"variant_{idx}.mid",
                        mime="audio/midi",
                        key=f"download_{idx}"
                    )
                with btn_col2:
                    if st.button("💾 保存标注", key=f"save_left_{idx}"):
                        current_s = st.session_state.get(f"s_{idx}", 0.5)
                        current_b = st.session_state.get(f"b_{idx}", 0.5)
                        current_f = st.session_state.get(f"f_{idx}", "")

                        while len(st.session_state.labels_surprise) <= idx:
                            st.session_state.labels_surprise.append(None)
                        while len(st.session_state.labels_beauty) <= idx:
                            st.session_state.labels_beauty.append(None)
                        while len(st.session_state.labels_feelings) <= idx:
                            st.session_state.labels_feelings.append("")
                        while len(st.session_state.save_indicator) <= idx:
                            st.session_state.save_indicator.append("")

                        st.session_state.labels_surprise[idx] = current_s
                        st.session_state.labels_beauty[idx] = current_b
                        st.session_state.labels_feelings[idx] = current_f
                        st.session_state.save_indicator[idx] = "✅"
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            with right_col:
                if idx < len(st.session_state.labels_surprise):
                    current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                else:
                    current_s = 0.5
                if idx < len(st.session_state.labels_beauty):
                    current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                else:
                    current_b = 0.5
                new_s = st.slider("意外度评分", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度评分", 0.0, 1.0, current_b, key=f"b_{idx}")
else:
    st.info("请在左侧上传MIDI文件并生成变体")
