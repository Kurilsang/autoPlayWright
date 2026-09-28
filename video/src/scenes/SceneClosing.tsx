import React from 'react';
import {AbsoluteFill} from 'remotion';
import {COLORS, FONT} from '../theme';
import {Reveal} from '../components/Reveal';
import {Chip} from '../components/Bits';

export const SceneClosing: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        fontFamily: FONT,
        color: COLORS.text,
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <Reveal delay={8} y={22}>
        <div
          style={{
            fontSize: 96,
            fontWeight: 850,
            letterSpacing: 2,
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
      <Reveal delay={28} y={18}>
        <div
          style={{
            marginTop: 18,
            fontSize: 40,
            fontWeight: 700,
            color: COLORS.text,
          }}
        >
          核心生产闭环：新增用例 ≈ 写/审一个 YAML
        </div>
      </Reveal>
      <Reveal delay={48} y={14}>
        <div
          style={{
            marginTop: 26,
            display: 'flex',
            gap: 16,
            justifyContent: 'center',
          }}
        >
          <Chip label="只断言确定性内容" tone="good" />
          <Chip label="失败即取证，禁止自愈" tone="warn" />
          <Chip label="AI 半自动 + 人工把关" tone="accent" />
        </div>
      </Reveal>
      <Reveal delay={72} y={12}>
        <div
          style={{
            marginTop: 64,
            fontSize: 30,
            color: COLORS.dim,
            letterSpacing: 4,
          }}
        >
          谢谢 · Q&A
        </div>
      </Reveal>
    </AbsoluteFill>
  );
};
