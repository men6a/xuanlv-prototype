import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
import re
from music21 import converter, note, stream, midi, chord, interval, pitch, meter, instrument

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
/* 侧边栏标题字体更小 */
.sidebar .sidebar-content h3 {
    font-size: 0.75rem !important;
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
st.markdown("上传MIDI文件，从动机发展出带左手柱式和弦的完整乐段，并标注听感。")

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
    
    # 2. 音程协和度矩阵
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
    def roman_or_num_to_degree(cls, token):
        """将罗马数字或阿拉伯数字转换为度数（0=I）"""
        token = token.strip()
        if token.isdigit():
            num = int(token)
            if 1 <= num <= 7:
                return num - 1
        roman_map = {
            'I': 0, 'II': 1, 'III': 2, 'IV': 3, 'V': 4, 'VI': 5, 'VII': 6,
            'i': 0, 'ii': 1, 'iii': 2, 'iv': 3, 'v': 4, 'vi': 5, 'vii': 6
        }
        base = re.match(r'^[IiVv]+', token)
        if base:
            return roman_map.get(base.group(), 0)
        return 0
    
    @classmethod
    def get_chord_tones(cls, chord_degree, key='C', mode='major'):
        """获取和弦内音（大三和弦）"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        root_pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        return {(root_pitch_class + offset) % 12 for offset in [0, 4, 7]}
    
    @classmethod
    def get_bass_note(cls, chord_degree, key='C', mode='major', octave=3):
        """获取和弦根音MIDI值"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        return octave * 12 + pitch_class
    
    @classmethod
    def interval_consonance(cls, interval):
        interval = abs(interval) % 12
        return cls.CONSONANCE_MATRIX.get(interval, 0.5)
    
    @classmethod
    def adjust_to_scale(cls, pitch, scale_notes):
        """将音高调整到最近的调内音"""
        if (pitch % 12) in scale_notes:
            return pitch
        best = pitch
        min_dist = 12
        for sn in scale_notes:
            for octave in [-1, 0, 1]:
                test = sn + ((pitch // 12) + octave) * 12
                dist = abs(test - pitch)
                if dist < min_dist and 0 <= test <= 127:
                    min_dist = dist
                    best = test
        return best
    
    @classmethod
    def adjust_to_chord(cls, pitch, chord_tones):
        """将音高调整到最近的和弦内音"""
        if (pitch % 12) in chord_tones:
            return pitch
        best = pitch
        min_dist = 12
        for ct in chord_tones:
            for octave in [-1, 0, 1]:
                test = ct + ((pitch // 12) + octave) * 12
                dist = abs(test - pitch)
                if dist < min_dist and 0 <= test <= 127:
                    min_dist = dist
                    best = test
        return best
    
    @classmethod
    def generate_melody_for_chord(cls, chord_duration, chord_tones, scale_notes, rhythm_pattern, style, motif_pitches, motif_weight, prev_pitch=None, motif_idx=0):
        """
        根据和弦和节奏模式生成旋律片段，并可混合动机音高
        motif_pitches: 动机音高序列（MIDI值列表）
        motif_weight: 动机保留度 (0-1)，概率使用动机音高
        返回 (音符列表, 最后一个音高, 新的动机索引)
        """
        style_params = {
            'classical': {'passing': 0.3, 'neighbor': 0.2, 'leap': 0.1},
            'jazz': {'passing': 0.4, 'neighbor': 0.3, 'leap': 0.2},
            'folk': {'passing': 0.2, 'neighbor': 0.2, 'leap': 0.1}
        }.get(style, {'passing': 0.3, 'neighbor': 0.2, 'leap': 0.1})
        
        total_pattern_dur = sum(rhythm_pattern)
        scale_factor = chord_duration / total_pattern_dur
        scaled_durs = [d * scale_factor for d in rhythm_pattern]
        
        notes = []
        current_time = 0.0
        last_pitch = prev_pitch
        
        for i, dur in enumerate(scaled_durs):
            # 根据权重决定是否使用动机音高
            use_motif = (random.random() < motif_weight) and motif_pitches
            if use_motif:
                # 取动机音高（循环索引）
                motif_pitch = motif_pitches[motif_idx % len(motif_pitches)]
                motif_idx += 1
                # 调整动机音高到最近的和弦内音
                pitch_val = cls.adjust_to_chord(motif_pitch, chord_tones)
                # 再确保在调内（以防和弦音不在调内？但和弦音应在调内）
                pitch_val = cls.adjust_to_scale(pitch_val, scale_notes)
            else:
                # 自由生成
                chord_tones_list = list(chord_tones)
                if random.random() < 0.7:  # 70%和弦音
                    pitch_class = random.choice(chord_tones_list)
                else:
                    scale_list = list(scale_notes)
                    non_chord = [p for p in scale_list if p not in chord_tones]
                    if non_chord:
                        pitch_class = random.choice(non_chord)
                    else:
                        pitch_class = random.choice(chord_tones_list)
                # 确定八度
                if last_pitch is not None:
                    best_pitch = None
                    min_dist = 100
                    for octave in range(2, 6):
                        candidate = octave * 12 + pitch_class
                        if 0 <= candidate <= 127:
                            dist = abs(candidate - last_pitch)
                            if dist < min_dist:
                                min_dist = dist
                                best_pitch = candidate
                    pitch_val = best_pitch
                else:
                    pitch_val = 60 + (pitch_class - 60 % 12)
                    if pitch_val < 48:
                        pitch_val += 12
                    elif pitch_val > 84:
                        pitch_val -= 12
            
            n = note.Note()
            n.pitch.midi = pitch_val
            n.quarterLength = dur
            n.offset = current_time
            notes.append(n)
            
            current_time += dur
            last_pitch = pitch_val
        
        return notes, last_pitch, motif_idx

# ==================== 动机发展功能（带左右手） ====================

def get_total_measures(stream_obj):
    """估算总小节数（基于offset）"""
    if not stream_obj:
        return 0
    max_offset = max(n.offset + n.quarterLength for n in stream_obj)
    return int(max_offset // 4) + 1

def extract_motif(notes, start_measure, length_measures):
    """从音符列表提取动机，返回音符列表和音高序列"""
    start_offset = (start_measure - 1) * 4.0
    end_offset = (start_measure + length_measures - 1) * 4.0
    motif_notes = [copy.deepcopy(n) for n in notes if n.offset >= start_offset and n.offset < end_offset]
    if not motif_notes:
        return None, None
    # 重置offset
    min_offset = min(n.offset for n in motif_notes)
    for n in motif_notes:
        n.offset -= min_offset
    motif_pitches = [n.pitch.midi for n in motif_notes]
    return motif_notes, motif_pitches

def extract_rhythm_pattern(motif_notes):
    return [n.quarterLength for n in motif_notes]

def apply_development_to_pitches(motif_pitches, technique, scale_notes):
    """对音高序列应用发展手法（倒影、逆行），返回新序列"""
    if technique == "重复":
        return motif_pitches[:]
    elif technique == "倒影":
        if not motif_pitches:
            return []
        axis = motif_pitches[0]
        new_pitches = []
        for p in motif_pitches:
            reflected = axis - (p - axis)
            reflected = MusicTheoryEngine.adjust_to_scale(reflected, scale_notes)
            new_pitches.append(reflected)
        return new_pitches
    elif technique == "逆行":
        return list(reversed(motif_pitches))
    else:
        return motif_pitches[:]

def develop_motif_with_progression_advanced(
    motif_notes, motif_pitches, target_measures, chord_sequence_str,
    chords_per_bar, development_technique, stretch_factor, motif_weight,
    key='C', mode='major', style='classical', beats_per_measure=4.0
):
    """
    根据和弦进程生成旋律，混合动机音高
    motif_weight: 动机保留度 (0-1)
    """
    if not motif_notes:
        return stream.Score()
    
    # 解析和弦序列
    tokens = [s.strip() for s in re.split(r'[,\s]+', chord_sequence_str) if s.strip()]
    if not tokens:
        return stream.Score()
    
    chord_degrees = [MusicTheoryEngine.roman_or_num_to_degree(tok) for tok in tokens]
    
    chord_duration_beats = beats_per_measure / chords_per_bar
    total_chords_needed = int(target_measures * chords_per_bar)
    
    chord_cycle = []
    for i in range(total_chords_needed):
        chord_cycle.append(chord_degrees[i % len(chord_degrees)])
    
    scale_notes = MusicTheoryEngine.get_scale_notes(key, mode)
    
    # 对动机音高应用发展手法
    developed_pitches = apply_development_to_pitches(motif_pitches, development_technique, scale_notes)
    # 对动机音符应用伸缩（节奏模式会从原始音符提取，但音高序列已经处理）
    if stretch_factor != 1.0:
        # 音高序列不变，但节奏会在后续用伸缩后的节奏模式
        pass
    
    # 提取节奏模式（从原始动机音符，未伸缩）
    rhythm_pattern = extract_rhythm_pattern(motif_notes)
    if stretch_factor != 1.0:
        rhythm_pattern = [d * stretch_factor for d in rhythm_pattern]
    
    # 创建左右手Part
    right_part = stream.Part()
    right_part.partName = "右手旋律"
    right_part.id = 'right'
    right_part.append(instrument.Piano())
    
    left_part = stream.Part()
    left_part.partName = "左手和弦"
    left_part.id = 'left'
    left_part.append(instrument.Piano())
    
    current_time = 0.0
    last_pitch = None
    motif_idx = 0  # 用于循环取动机音高
    
    for chord_idx, chord_degree in enumerate(chord_cycle):
        chord_tones = MusicTheoryEngine.get_chord_tones(chord_degree, key, mode)
        
        # 生成旋律片段，混合动机音高
        melody_notes, last_pitch, motif_idx = MusicTheoryEngine.generate_melody_for_chord(
            chord_duration_beats, chord_tones, scale_notes, rhythm_pattern, style,
            developed_pitches, motif_weight, last_pitch, motif_idx
        )
        
        for n in melody_notes:
            new_n = copy.deepcopy(n)
            new_n.offset = current_time + n.offset
            right_part.append(new_n)
        
        # 左手和弦
        root = MusicTheoryEngine.get_bass_note(chord_degree, key, mode, octave=3)
        third = root + 4
        fifth = root + 7
        left_chord = chord.Chord([root, third, fifth])
        left_chord.quarterLength = chord_duration_beats
        left_chord.offset = current_time
        left_chord.volume.velocity = 84
        left_part.append(left_chord)
        
        current_time += chord_duration_beats
    
    score = stream.Score()
    score.append(right_part)
    score.append(left_part)
    return score

# ==================== 辅助函数 ====================

def get_midi_bytes(score):
    temp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
    mf = midi.translate.music21ObjectToMidiFile(score)
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
    raw_melodies = []  # 存储原始旋律的note列表
    if uploaded_files:
        for f in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            try:
                score = converter.parse(tmp_path)
                note_list = list(score.parts[0].flat.getElementsByClass(note.Note))
                if note_list:
                    raw_melodies.append(note_list)
                    st.success(f"已导入: {f.name}")
                else:
                    st.warning(f"无音符: {f.name}")
            except Exception as e:
                st.error(f"解析失败: {f.name} - {str(e)}")
            import os
            os.unlink(tmp_path)

    st.markdown("### 2. 动机发展")
    if raw_melodies:
        # 估算总小节数
        total_measures_est = get_total_measures(raw_melodies[0])
        st.caption(f"当前MIDI估算总小节数: {total_measures_est}")
        
        key_options = ['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab']
        selected_key = st.selectbox("调性", key_options, index=0)
        
        mode_options = ['major', 'minor', 'harmonic_minor', 'melodic_minor', 'dorian', 'mixolydian']
        selected_mode = st.selectbox("调式", mode_options, index=0)
        
        style_options = ['classical', 'jazz', 'folk']
        selected_style = st.selectbox("风格", style_options, index=0)
        
        start_measure = st.number_input("起始小节", min_value=1, max_value=max(1, total_measures_est), value=1)
        motif_length = st.number_input("动机长度（小节）", min_value=1, max_value=16, value=2)
        target_length = st.number_input("目标乐段长度（小节）", min_value=1, max_value=64, value=18)
        
        default_prog = "1,4,5,1"
        chord_prog_input = st.text_input("和弦进程（罗马数字或阿拉伯数字，逗号或空格分隔）", value=default_prog)
        
        chords_per_bar = st.selectbox("每小节和弦数", [1, 2, 3, 4], index=0)
        dev_technique = st.selectbox("发展手法", ["重复", "倒影", "逆行"], index=0)
        stretch_factor = st.slider("节奏伸缩因子", 0.5, 2.0, 1.0, step=0.1)
        
        # 新增：动机保留度滑块
        motif_weight = st.slider("动机保留度", 0.0, 1.0, 0.5, step=0.05,
                                 help="0：完全基于和弦生成旋律；1：尽可能使用动机音高（并调整到当前和弦）")
        
        if st.button("生成带伴奏的乐段"):
            if not raw_melodies:
                st.warning("请先导入MIDI")
            else:
                source_notes = raw_melodies[0]
                motif_notes, motif_pitches = extract_motif(source_notes, start_measure, motif_length)
                if not motif_notes:
                    st.error("指定小节内无音符，请调整范围")
                else:
                    developed_score = develop_motif_with_progression_advanced(
                        motif_notes, motif_pitches, target_length, chord_prog_input,
                        chords_per_bar, dev_technique, stretch_factor, motif_weight,
                        key=selected_key, mode=selected_mode, style=selected_style, beats_per_measure=4.0
                    )
                    new_idx = len(st.session_state.variants)
                    st.session_state.variants.append(developed_score)
                    st.session_state.variant_meta.append({
                        'type': 'development_advanced',
                        'start_measure': start_measure,
                        'motif_length': motif_length,
                        'target_length': target_length,
                        'chord_prog': chord_prog_input,
                        'chords_per_bar': chords_per_bar,
                        'technique': dev_technique,
                        'stretch': stretch_factor,
                        'motif_weight': motif_weight,
                        'key': selected_key,
                        'mode': selected_mode,
                        'style': selected_style
                    })
                    st.session_state.labels_surprise.append(None)
                    st.session_state.labels_beauty.append(None)
                    st.session_state.labels_feelings.append("")
                    st.session_state.save_indicator.append("")
                    st.success(f"已生成带伴奏的乐段，作为变体 #{new_idx} 添加")
    else:
        st.info("请先导入MIDI文件")

# ==================== 主界面 ====================

if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):
        indicator = st.session_state.save_indicator[idx] if idx < len(st.session_state.save_indicator) else ""
        meta = st.session_state.variant_meta[idx] if idx < len(st.session_state.variant_meta) else {}
        
        if meta:
            param_str = (f"动机发展: {meta.get('start_measure')}小节起{meta.get('motif_length')}小节 → {meta.get('target_length')}小节 | "
                         f"调性:{meta.get('key','C')} {meta.get('mode','major')} {meta.get('style','classical')} | "
                         f"和弦:{meta.get('chord_prog')} | 密度:{meta.get('chords_per_bar')}/小节 | "
                         f"手法:{meta.get('technique')} | 伸缩:{meta.get('stretch')} | "
                         f"动机保留:{meta.get('motif_weight',0.5):.2f}")
        else:
            param_str = "变体"
        
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
    st.info("请在左侧上传MIDI文件，并在动机发展中生成带伴奏的乐段")
