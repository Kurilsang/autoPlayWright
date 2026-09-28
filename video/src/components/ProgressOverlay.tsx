import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import {COLORS, FONT} from '../theme';
import {SCENES, TOTAL_DURATION} from '../timing';

/** 全局水印 + 章节标签 + 底部进度条。 */
export const ProgressOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, TOTAL_DURATION], [0, 1], {
    extrapolateRight: 'clamp',
    easing: Easing.linear,
  });

  let current = SCENES[0];
  let offset = 0;
  for (const s of SCENES) {
    if (frame >= offset) current = s;
    offset += s.duration;
  }

  return (
    <AbsoluteFill style={{pointerEvents: 'none', fontFamily: FONT}}>
      <div
        style={{
          position: 'absolute',
          top: 36,
          right: 120,
          fontSize: 20,
          letterSpacing: 1,
          color: COLORS.faint,
          fontWeight: 650,
        }}
      >
        autoPlayWright · 项目报告 · {current.chapter} {current.nav}
      </div>
      <div
        style={{
          position: 'absolute',
          left: 120,
          right: 120,
          bottom: 52,
          height: 6,
          borderRadius: 3,
          background: 'rgba(159,176,204,0.18)',
        }}
      >
        <div
          style={{
            width: `${progress * 100}%`,
            height: '100%',
            borderRadius: 3,
            background: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accent2})`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
