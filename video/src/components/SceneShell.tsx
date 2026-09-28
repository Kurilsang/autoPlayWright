import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {COLORS, FONT} from '../theme';
import {Reveal} from './Reveal';

/** 章节页骨架：章节徽标 + 大标题 + 内容区。整页淡入淡出由 SceneWrap 负责。 */
export const SceneShell: React.FC<{
  chapter: string;
  title: string;
  subtitle?: string;
  duration: number;
  children: React.ReactNode;
}> = ({chapter, title, subtitle, children}) => {
  return (
    <AbsoluteFill
      style={{
        padding: '92px 120px 110px',
        fontFamily: FONT,
        color: COLORS.text,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 22}}>
        <div
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: 2,
            color: COLORS.accent,
            border: '1.5px solid rgba(91,140,255,0.5)',
            borderRadius: 12,
            padding: '6px 16px',
            background: 'rgba(91,140,255,0.10)',
          }}
        >
          {chapter}
        </div>
        <Reveal delay={2} y={14}>
          <div
            style={{
              fontSize: 62,
              fontWeight: 800,
              letterSpacing: 1,
              lineHeight: 1.15,
            }}
          >
            {title}
          </div>
        </Reveal>
      </div>
      {subtitle ? (
        <Reveal delay={10} y={12}>
          <div
            style={{
              marginTop: 16,
              fontSize: 27,
              color: COLORS.dim,
              lineHeight: 1.5,
              maxWidth: 1500,
            }}
          >
            {subtitle}
          </div>
        </Reveal>
      ) : null}
      <div style={{marginTop: 46, flex: 1, minHeight: 0}}>{children}</div>
    </AbsoluteFill>
  );
};

/** 场景容器：负责整页淡入淡出过渡，内部再放场景内容。 */
export const SceneWrap: React.FC<{
  duration: number;
  children: React.ReactNode;
}> = ({duration, children}) => {
  return (
    <AbsoluteFill>
      <FadeFrame duration={duration}>{children}</FadeFrame>
    </AbsoluteFill>
  );
};

const FadeFrame: React.FC<{duration: number; children: React.ReactNode}> = ({
  duration,
  children,
}) => {
  const frame = useCurrentFrame();
  const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
  const fadeIn = clamp01(frame / 9);
  const fadeOut = clamp01((duration - frame) / 12);
  return <AbsoluteFill style={{opacity: fadeIn * fadeOut}}>{children}</AbsoluteFill>;
};
