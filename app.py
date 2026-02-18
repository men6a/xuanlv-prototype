import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
from music21 import converter, note, stream, midi, chord, interval, pitch
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
/* 侧边栏标题字体再小两号 */
.sidebar .sidebar-content h3 {
    font-size: 0.85rem !important;
    font-weight: 600;
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

# ==================== 全维度音乐理论规则库 ====================

class MusicTheoryEngine:
    """音乐理论引擎：整合最新研究成果"""
    
    # 1. 调式音阶定义 
    SCALES = {
        'major': [0, 2, 4, 5, 7, 9, 11],     # 大调音阶
        'minor': [0, 2, 3, 5, 7, 8, 10],     # 自然小调
        'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],  # 和声小调
        'melodic_minor': [0, 2, 3, 5, 7, 9, 11],   # 旋律小调上行
        'dorian': [0, 2, 3, 5, 7, 9, 10],    # 多利亚调式
        'mixolydian': [0, 2, 4, 5, 7, 9, 10], # 混合利底亚
    }
    
    # 2. 和声进行规则 
    HARMONIC_PROGRESSIONS = {
        'authentic': ['I', 'V', 'I'],           # 正格进行
        'plagal': ['I', 'IV', 'I'],             # 变格进行
        'deceptive': ['V', 'vi'],                # 阻碍进行
        'circle': ['I', 'IV', 'vii°', 'iii', 'vi', 'ii', 'V', 'I'],  # 五度圈
    }
    
    # 3. 声部进行规则
    VOICE_LEADING = {
        'max_interval': 12,
        'prefer_step': 0.6,
        'prefer_skip': 0.3,
        'prefer_leap': 0.1,
        'contrary_motion': 0.4,
    }
    
    # 4. 风格一致性参数
    STYLE_CONSISTENCY = {
        'classical': {
            'ornament_prob': 0.3,
            'sequence_prob': 0.4,
            'repeat_prob': 0.3,
            'dissonance_tolerance': 0.2
        },
        'jazz': {
            'ornament_prob': 0.5,
            'sequence_prob': 0.2,
            'repeat_prob': 0.2,
            'dissonance_tolerance': 0.6
        },
        'folk': {
            'ornament_prob': 0.2,
            'sequence_prob': 0.3,
            'repeat_prob': 0.4,
            'dissonance_tolerance': 0.1
        }
    }
    
    # 5. 音程协和度矩阵
    CONSONANCE_MATRIX = {
        0: 1.0, 12: 1.0,
        7: 0.9, 19: 0.9,
        5: 0.8, 17: 0.8,
        4: 0.8, 3: 0.75, 16: 0.8, 15: 0.75,
        9: 0.7, 8: 0.65, 21: 0.7, 20: 0.65,
        2: 0.4, 10: 0.4, 14: 0.4, 22: 0.4,
        1: 0.1, 11: 0.1, 13: 0.1, 23: 0.1,
        6: 0.0, 18: 0.0
    }
    
    # 6. 常用和弦进程（罗马数字表示，相对于主音）
    COMMON_PROGRESSIONS = {
        "I-IV-V-I": [0, 5, 7, 0],      # I, IV, V, I
        "I-V-vi-IV": [0, 7, 9, 5],     # I, V, vi, IV
        "ii-V-I": [2, 7, 0],           # ii, V, I
        "I-vi-IV-V": [0, 9, 5, 7],     # I, vi, IV, V
    }
    
    @classmethod
    def get_scale_notes(cls, key, mode):
        """获取指定调性的音阶音符（MIDI模12）"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root = note_to_idx.get(key, 0)
        scale_pattern = cls.SCALES.get(mode, cls.SCALES['major'])
        return {(root + interval) % 12 for interval in scale_pattern}
    
    @classmethod
    def get_chord_tones(cls, chord_degree, key='C', mode='major'):
        """
        根据罗马数字和弦级数获取和弦内音（MIDI模12）
        chord_degree: 和弦级数索引（0=I, 1=II, 2=III, ...）
        简单实现：大三和弦（根音、根音+4、根音+7）
        """
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        # 根据级数计算根音的音级（相对于主音）
        # 假设大调：I=0, II=2, III=4, IV=5, V=7, VI=9, VII=11
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        root_pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        # 大三和弦：根音、根音+4、根音+7
        return {(root_pitch_class + offset) % 12 for offset in [0, 4, 7]}
    
    @classmethod
    def interval_consonance(cls, interval):
        interval = abs(interval) % 12
        return cls.CONSONANCE_MATRIX.get(interval, 0.5)
    
    @classmethod
    def voice_leading_score(cls, prev_pitch, new_pitch, other_voices=None):
        interval = abs(new_pitch - prev_pitch)
        if interval <= 2:
            score = 1.0
        elif interval <= 5:
            score = 0.7
        elif interval <= 8:
            score = 0.4
        else:
            score = 0.2
        consonance = cls.interval_consonance(interval)
        score = score * 0.6 + consonance * 0.4
        if other_voices:
            for voice in other_voices:
                if abs(voice - new_pitch) % 12 in [0, 7]:
                    score *= 0.5
        return score

# ==================== 增强版生成变体函数 ====================

def generate_variant(melody_stream, surprise_strength=0.3,
                     key='C', mode='major', style='classical',
                     progression=None):
    """
    融合多维度音乐规则的旋律变体生成 v3.2
    修复了装饰音替换导致的索引越界问题
    """
    # 获取音阶
    scale_notes = MusicTheoryEngine.get_scale_notes(key, mode)
    style_params = MusicTheoryEngine.STYLE_CONSISTENCY.get(style, MusicTheoryEngine.STYLE_CONSISTENCY['classical'])
    
    # 音程概率分布
    INTERVAL_WEIGHTS = {
        1: 0.35, 2: 0.25, 3: 0.15, 4: 0.10,
        5: 0.08, 6: 0.05, 7: 0.02,
    }
    
    # 节奏模式库
    RHYTHM_PATTERNS = {
        'classical': [1, 0.5, 0.5, 1, 1, 2, 1.5, 0.5],
        'jazz': [0.5, 0.5, 1, 1.5, 0.5, 1, 2, 1],
        'folk': [1, 1, 0.5, 0.5, 1, 2, 1, 1],
    }
    COMMON_DURS = [0.25, 0.5, 1, 1.5, 2, 3, 4]
    
    # 装饰音模式
    ORNAMENTS = {
        'trill': lambda p: [p, p+2, p, p+2, p],
        'turn': lambda p: [p, p+1, p, p-1, p],
        'mordent': lambda p: [p, p+1, p],
        'appoggiatura': lambda p: [p+2, p],
    }
    
    # 解析和弦进程
    progression_tones = None
    if progression and progression != "无":
        prog_degrees = MusicTheoryEngine.COMMON_PROGRESSIONS.get(progression, [0,5,7,0])
        # 计算每个和弦的音高集合
        prog_chords = []
        for degree in prog_degrees:
            chord_tones = MusicTheoryEngine.get_chord_tones(degree, key, mode)
            prog_chords.append(chord_tones)
        progression_tones = prog_chords  # 列表，每个元素是一个set
        # 假设每4拍换一个和弦
        bar_length = 4.0  # 每小节4拍（四分音符为单位）
    
    original_notes = list(melody_stream.getElementsByClass(note.Note))
    if not original_notes:
        return stream.Stream()
    
    # 获取每个音符的起始时间（offset）
    offsets = [n.offset for n in original_notes]
    
    new_notes = [copy.deepcopy(n) for n in original_notes]
    
    # 分析原始旋律特征
    original_pitches = [n.pitch.midi for n in original_notes]
    avg_pitch = np.mean(original_pitches) if original_pitches else 60
    pitch_range = max(original_pitches) - min(original_pitches) if original_pitches else 12
    
    # 构建其他声部上下文
    other_voices = []
    for i in range(max(1, len(new_notes) // 4)):
        if i < len(original_pitches):
            other_voices.append(original_pitches[i] + random.choice([-12, 0, 12]))
    
    n_changes = max(1, int(len(new_notes) * surprise_strength))
    
    # 主循环
    for _ in range(n_changes):
        if len(new_notes) == 0:
            break
        idx = random.randint(0, len(new_notes)-1)
        current_note = new_notes[idx]
        current_pitch = current_note.pitch.midi
        current_dur = current_note.quarterLength
        
        # 确保 offsets 和 new_notes 长度一致（重新计算）
        if len(offsets) != len(new_notes):
            # 重新计算 offsets：从0开始累加时值
            new_offsets = [0.0]
            for i in range(1, len(new_notes)):
                new_offsets.append(new_offsets[i-1] + new_notes[i-1].quarterLength)
            offsets = new_offsets
        
        current_offset = offsets[idx] if idx < len(offsets) else 0.0
        
        modify_type = random.choices(
            ['pitch', 'rhythm', 'both', 'ornament'],
            weights=[0.4, 0.2, 0.2, 0.2]
        )[0]
        
        # ----- 装饰音处理 -----
        if modify_type == 'ornament' and random.random() < style_params['ornament_prob']:
            ornament_type = random.choice(list(ORNAMENTS.keys()))
            ornament_notes = ORNAMENTS[ornament_type](current_pitch)
            ornament_stream = []
            sub_dur = current_dur / len(ornament_notes)
            for i, p in enumerate(ornament_notes):
                new_n = note.Note()
                new_n.pitch.midi = p
                new_n.quarterLength = sub_dur
                ornament_stream.append(new_n)
            # 替换原音符
            new_notes[idx:idx+1] = ornament_stream
            # 重新计算 offsets（将在下一轮循环中更新）
            # 继续下一轮循环，不再处理当前索引的其他修改
            continue
        
        # ----- 音高修改 -----
        if modify_type in ['pitch', 'both']:
            interval_probs = list(INTERVAL_WEIGHTS.values())
            if surprise_strength > 0.7:
                interval_probs = [p * (1 + surprise_strength) for p in interval_probs]
            interval = random.choices(list(INTERVAL_WEIGHTS.keys()), weights=interval_probs)[0]
            
            if idx > 0:
                prev_pitch = new_notes[idx-1].pitch.midi if idx-1 < len(new_notes) else current_pitch
                if current_pitch > prev_pitch:
                    dir_weights = {'up': 0.5, 'down': 0.3, 'same': 0.2}
                elif current_pitch < prev_pitch:
                    dir_weights = {'up': 0.3, 'down': 0.5, 'same': 0.2}
                else:
                    dir_weights = {'up': 0.3, 'down': 0.3, 'same': 0.4}
            else:
                dir_weights = {'up': 0.3, 'down': 0.3, 'same': 0.4}
            
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
            
            # 调性约束
            if (candidate % 12) not in scale_notes:
                best_candidate = candidate
                min_dist = 12
                for scale_note in scale_notes:
                    for octave in [-1, 0, 1]:
                        test_pitch = scale_note + ((candidate // 12) + octave) * 12
                        dist = abs(test_pitch - candidate)
                        if dist < min_dist and 0 <= test_pitch <= 127:
                            min_dist = dist
                            best_candidate = test_pitch
                candidate = best_candidate
            
            # 和弦进程约束：强拍位置优先使用和弦内音
            if progression_tones is not None:
                # 计算当前音符属于第几个和弦（假设每4拍一个和弦）
                bar_index = int(current_offset // 4)
                chord_idx = bar_index % len(progression_tones)
                chord_tones = progression_tones[chord_idx]
                # 检查candidate是否在和弦内
                if (candidate % 12) not in chord_tones and random.random() > surprise_strength:
                    # 调整到最近的和弦内音
                    best_pitch = candidate
                    min_dist = 12
                    for ct in chord_tones:
                        for octave in [-1, 0, 1]:
                            test_pitch = ct + ((candidate // 12) + octave) * 12
                            dist = abs(test_pitch - candidate)
                            if dist < min_dist and 0 <= test_pitch <= 127:
                                min_dist = dist
                                best_pitch = test_pitch
                    candidate = best_pitch
            
            # 声部进行评分
            if idx > 0 and idx < len(new_notes):
                prev_pitch = new_notes[idx-1].pitch.midi
                voice_score = MusicTheoryEngine.voice_leading_score(prev_pitch, candidate, other_voices)
                if voice_score < 0.3 and random.random() > surprise_strength:
                    continue
            
            # 音域约束
            if abs(candidate - avg_pitch) > pitch_range * 1.5 and random.random() > surprise_strength:
                candidate = int(avg_pitch + (candidate - avg_pitch) * 0.5)
            
            if 0 <= candidate <= 127:
                current_note.pitch.midi = candidate
        
        # ----- 节奏修改 -----
        if modify_type in ['rhythm', 'both']:
            if random.random() < 0.5:
                pattern = RHYTHM_PATTERNS.get(style, RHYTHM_PATTERNS['classical'])
                new_dur = random.choice(pattern)
            else:
                possible_durs = [d for d in COMMON_DURS if abs(d - current_dur) > 0.1]
                new_dur = random.choice(possible_durs) if possible_durs else current_dur
            new_dur = max(0.25, min(8, new_dur))
            current_note.quarterLength = new_dur
    
    # 模进处理
    if random.random() < style_params['sequence_prob'] * surprise_strength:
        if len(new_notes) > 4:
            seq_start = random.randint(0, len(new_notes)-4)
            seq_len = random.randint(2, 4)
            seq_interval = random.choice([2, 4, 5, 7, -2, -4, -5, -7])
            for i in range(seq_len):
                if seq_start + i + seq_len < len(new_notes):
                    src_note = new_notes[seq_start + i]
                    tgt_idx = seq_start + i + seq_len
                    new_pitch = src_note.pitch.midi + seq_interval
                    if (new_pitch % 12) in scale_notes and 0 <= new_pitch <= 127:
                        new_notes[tgt_idx].pitch.midi = new_pitch
    
    new_stream = stream.Stream()
    for n in new_notes:
        new_stream.append(n)
    return new_stream

# ==================== 辅助函数 ====================

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

# ==================== 侧边栏UI ====================

with st.sidebar:
    st.markdown("### 1. 导入MIDI文件")
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

    st.markdown("### 2. 选择音乐参数")
    key_options = ['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab']
    selected_key = st.selectbox("调性", key_options, index=0)
    
    mode_options = ['major', 'minor', 'harmonic_minor', 'melodic_minor', 'dorian', 'mixolydian']
    selected_mode = st.selectbox("调式", mode_options, index=0)
    
    style_options = ['classical', 'jazz', 'folk']
    selected_style = st.selectbox("风格", style_options, index=0)
    
    # 和弦进程选择
    progression_options = ["无"] + list(MusicTheoryEngine.COMMON_PROGRESSIONS.keys())
    selected_progression = st.selectbox("和弦进程", progression_options, index=0)

    st.markdown("### 3. 生成变体")
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
                    var = generate_variant(
                        mel,
                        strength,
                        key=selected_key,
                        mode=selected_mode,
                        style=selected_style,
                        progression=None if selected_progression == "无" else selected_progression
                    )
                    new_variants.append(var)
                    new_meta.append({
                        'original_idx': len(raw_melodies)-1,
                        'surprise_strength': strength,
                        'key': selected_key,
                        'mode': selected_mode,
                        'style': selected_style,
                        'progression': selected_progression
                    })
            st.session_state.variants = new_variants
            st.session_state.variant_meta = new_meta
            st.session_state.labels_surprise = [None] * len(new_variants)
            st.session_state.labels_beauty = [None] * len(new_variants)
            st.session_state.labels_feelings = [""] * len(new_variants)
            st.session_state.save_indicator = [""] * len(new_variants)
            st.success(f"已生成 {len(new_variants)} 个变体")

# ==================== 主界面 ====================

if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):
        indicator = st.session_state.save_indicator[idx] if idx < len(st.session_state.save_indicator) else ""
        meta = st.session_state.variant_meta[idx] if idx < len(st.session_state.variant_meta) else {}
        prog_str = meta.get('progression', '无')
        param_str = f"{meta.get('key','C')} {meta.get('mode','major')} {meta.get('style','classical')} {prog_str}" if meta else ""
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
