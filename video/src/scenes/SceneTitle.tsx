import React from 'react';
import {AbsoluteFill} from 'remotion';
import {COLORS, FONT} from '../theme';
import {Reveal} from '../components/Reveal';
import {Chip} from '../components/Bits';

export const SceneTitle: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        fontFamily: FONT,
        color: COLORS.text,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <Reveal delay={6} y={18}>
        <div
          style={{
            fontSize: 26,
            letterSpacing: 6,
            color: COLORS.accent2,
            fontWeight: 700,
          }}
        >
          内部 AGENT 产品 · WEB + ELECTRON
        </div>
      </Reveal>
      <Reveal delay={18} y={30}>
        <div
          style={{
            marginTop: 26,
            fontSize: 132,
            fontWeight: 850,
            letterSpacing: 2,
            lineHeight: 1.1,
            background:
              'linear-gradient(92deg, #EAF0FF 20%, #8FB4FF 55%, #37D6A6 95%)',
            WebkitBackgroundClip: 'text',
            backgroundClip: 'text',
            color: 'transparent',
          }}
        >
          autoPlayWright
        </div>
      </Reveal>
      <Reveal delay={36} y={22}>
        <div
          style={{
            marginTop: 20,
            fontSize: 42,
            fontWeight: 650,
            color: COLORS.dim,
            letterSpacing: 2,
          }}
        >
          UI 自动化测试框架 · 项目报告
        </div>
      </Reveal>
      <Reveal delay={56} y={16}>
        <div
          style={{
            marginTop: 56,
            display: 'flex',
            gap: 16,
            justifyContent: 'center',
          }}
        >
          <Chip label="YAML DSL 描述链路" tone="accent" />
          <Chip label="pytest 解释执行" tone="good" />
          <Chip label="JSON + HTML 报告" tone="accent" />
          <Chip label="AI 半自动生成" tone="warn" />
        </div>
      </Reveal>
    </AbsoluteFill>
  );
};
