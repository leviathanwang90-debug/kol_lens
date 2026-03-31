/*
 * Design: Dark Constellation (暗夜星图)
 * Color: Deep Space Black #080808 + Brand Red #D4001A + Warm Gold #FFB800
 * Typography: Bebas Neue (display) + Space Grotesk (body) + Orbitron (data) + Noto Sans SC (Chinese)
 * Signature: Particle constellation bg, red glow effects, scanline overlay
 */

import { Navbar } from "@/components/Navbar";
import { ParticleBackground } from "@/components/ParticleBackground";
import { ASSETS, PRODUCT_NAME, PRODUCT_SUBTITLE } from "@/lib/constants";
import { motion } from "framer-motion";
import { Link } from "wouter";
import {
  Brain,
  BarChart3,
  Database,
  FileSpreadsheet,
  Zap,
  Target,
  ArrowRight,
  Sparkles,
  Search,
  Users,
  TrendingUp,
} from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number] },
  }),
};

const features = [
  {
    icon: Brain,
    title: "AI 意图解析",
    desc: "自然语言输入需求，AI 自动解析为结构化筛选条件，支持权重调节与宽容度控制",
    image: ASSETS.featureAi,
  },
  {
    icon: BarChart3,
    title: "34维数据矩阵",
    desc: "覆盖基础数据、日常大盘、图文/视频表现、合作转化、预估报价六大维度",
    image: ASSETS.featureData,
  },
  {
    icon: Database,
    title: "达人资产库",
    desc: "智能打标与双轨资产图谱，沉淀品牌专属达人资产，支持履约全链路追踪",
    image: ASSETS.featureLibrary,
  },
];

const stats = [
  { value: "34", label: "数据维度", suffix: "维" },
  { value: "6", label: "分析视图", suffix: "组" },
  { value: "<3", label: "意图解析", suffix: "秒" },
  { value: "∞", label: "弹性寻回", suffix: "" },
];

const workflow = [
  { step: "01", icon: Search, title: "需求录入", desc: "自然语言描述你的达人需求" },
  { step: "02", icon: Sparkles, title: "智能匹配", desc: "AI解析意图并弹性寻回达人" },
  { step: "03", icon: Target, title: "沉浸评审", desc: "连续翻牌式评审与决策" },
  { step: "04", icon: TrendingUp, title: "进化迭代", desc: "基于反馈进化检索策略" },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-background text-foreground overflow-hidden">
      <Navbar />

      {/* ===== HERO SECTION ===== */}
      <section className="relative min-h-screen flex items-center justify-center pt-16">
        {/* Background layers */}
        <div className="absolute inset-0">
          <img
            src={ASSETS.heroBg}
            alt=""
            className="w-full h-full object-cover opacity-40"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-background/60 via-background/40 to-background" />
        </div>
        <ParticleBackground className="z-[1] opacity-60" />

        {/* Scanline overlay */}
        <div className="absolute inset-0 scanlines z-[2]" />

        {/* Content */}
        <div className="relative z-10 container text-center">
          <motion.div
            initial="hidden"
            animate="visible"
            className="max-w-4xl mx-auto"
          >
            {/* Brand badge */}
            <motion.div custom={0} variants={fadeUp} className="mb-8">
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-primary/30 bg-primary/5 text-sm text-primary font-medium">
                <Zap className="w-3.5 h-3.5" />
                Powered by Σ.magic
              </span>
            </motion.div>

            {/* Main title */}
            <motion.h1
              custom={1}
              variants={fadeUp}
              className="font-display text-6xl sm:text-7xl md:text-8xl lg:text-9xl tracking-wider leading-none mb-6"
            >
              <span className="text-foreground">Σ.</span>
              <span className="text-primary text-glow-red">MATCH</span>
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              custom={2}
              variants={fadeUp}
              className="font-chinese text-lg sm:text-xl md:text-2xl text-muted-foreground mb-4 tracking-wide"
            >
              智能寻星工作站
            </motion.p>

            <motion.p
              custom={3}
              variants={fadeUp}
              className="font-chinese text-sm sm:text-base text-muted-foreground/70 max-w-2xl mx-auto mb-12 leading-relaxed"
            >
              {PRODUCT_SUBTITLE}
              <br />
              自然语言驱动 · 多维数据透视 · 沉浸式评审 · 资产自动化沉淀
            </motion.p>

            {/* CTA Buttons */}
            <motion.div custom={4} variants={fadeUp} className="flex items-center justify-center gap-4 flex-wrap">
              <Link href="/workspace">
                <span className="inline-flex items-center gap-2 px-8 py-3.5 text-base font-semibold text-primary-foreground bg-primary rounded-lg hover:bg-primary/90 transition-all glow-red-strong group">
                  开始寻星
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </span>
              </Link>
              <Link href="/library">
                <span className="inline-flex items-center gap-2 px-8 py-3.5 text-base font-medium text-foreground border border-border rounded-lg hover:border-primary/50 hover:bg-primary/5 transition-all">
                  达人资产库
                </span>
              </Link>
            </motion.div>
          </motion.div>

          {/* Stats bar */}
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            className="mt-20 max-w-3xl mx-auto"
          >
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {stats.map((stat, i) => (
                <div key={i} className="text-center">
                  <div className="font-data text-3xl md:text-4xl font-bold text-primary text-glow-red">
                    {stat.value}
                    <span className="text-lg text-primary/70">{stat.suffix}</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1 font-chinese">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Bottom gradient fade */}
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-background to-transparent z-[3]" />
      </section>

      {/* ===== WORKFLOW SECTION ===== */}
      <section className="relative py-32">
        <div className="container">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-20"
          >
            <span className="text-xs font-data tracking-[0.3em] text-primary/70 uppercase">
              Workflow
            </span>
            <h2 className="font-display text-4xl md:text-5xl tracking-wider mt-3 mb-4">
              寻星工作流
            </h2>
            <p className="text-muted-foreground font-chinese max-w-xl mx-auto">
              从需求录入到资产沉淀，四步完成高效达人匹配
            </p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 max-w-5xl mx-auto">
            {workflow.map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.15, duration: 0.5 }}
                className="relative group"
              >
                <div className="glass-panel rounded-xl p-6 h-full transition-all hover:border-primary/40 breathe-border">
                  {/* Step number */}
                  <div className="font-data text-4xl font-bold text-primary/20 mb-4">
                    {item.step}
                  </div>
                  {/* Icon */}
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <item.icon className="w-5 h-5 text-primary" />
                  </div>
                  <h3 className="font-semibold text-foreground mb-2 font-chinese">
                    {item.title}
                  </h3>
                  <p className="text-sm text-muted-foreground font-chinese leading-relaxed">
                    {item.desc}
                  </p>
                </div>
                {/* Connector line */}
                {i < workflow.length - 1 && (
                  <div className="hidden md:block absolute top-1/2 -right-3 w-6 h-px bg-gradient-to-r from-primary/40 to-transparent" />
                )}
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== FEATURES SECTION ===== */}
      <section className="relative py-32">
        <div className="container">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-20"
          >
            <span className="text-xs font-data tracking-[0.3em] text-primary/70 uppercase">
              Core Features
            </span>
            <h2 className="font-display text-4xl md:text-5xl tracking-wider mt-3 mb-4">
              核心能力
            </h2>
            <p className="text-muted-foreground font-chinese max-w-xl mx-auto">
              三大核心模块，覆盖达人匹配全链路
            </p>
          </motion.div>

          <div className="space-y-24 max-w-6xl mx-auto">
            {features.map((feature, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ duration: 0.7 }}
                className={`flex flex-col ${
                  i % 2 === 0 ? "lg:flex-row" : "lg:flex-row-reverse"
                } items-center gap-12`}
              >
                {/* Image */}
                <div className="flex-1 w-full">
                  <div className="relative rounded-2xl overflow-hidden glow-red group">
                    <img
                      src={feature.image}
                      alt={feature.title}
                      className="w-full aspect-square object-cover transition-transform duration-700 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent" />
                  </div>
                </div>

                {/* Text */}
                <div className="flex-1 w-full">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
                      <feature.icon className="w-6 h-6 text-primary" />
                    </div>
                    <h3 className="font-display text-3xl tracking-wider">
                      {feature.title}
                    </h3>
                  </div>
                  <p className="text-muted-foreground font-chinese text-base leading-relaxed mb-6">
                    {feature.desc}
                  </p>
                  <Link href="/workspace">
                    <span className="inline-flex items-center gap-2 text-sm text-primary hover:text-primary/80 transition-colors group">
                      了解更多
                      <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
                    </span>
                  </Link>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== DATA DIMENSIONS SECTION ===== */}
      <section className="relative py-32">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/[0.02] to-transparent" />
        <div className="container relative">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-16"
          >
            <span className="text-xs font-data tracking-[0.3em] text-primary/70 uppercase">
              Data Dimensions
            </span>
            <h2 className="font-display text-4xl md:text-5xl tracking-wider mt-3 mb-4">
              34维数据全景
            </h2>
            <p className="text-muted-foreground font-chinese max-w-xl mx-auto">
              六大分析视图，全方位透视达人价值
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
            {[
              { icon: Users, label: "基础视图", count: 6, desc: "粉丝画像与活跃度" },
              { icon: BarChart3, label: "日常大盘", count: 5, desc: "曝光·阅读·互动中位数" },
              { icon: FileSpreadsheet, label: "图文表现", count: 5, desc: "图文内容数据深度" },
              { icon: Zap, label: "视频表现", count: 6, desc: "视频完播与互动分析" },
              { icon: TrendingUp, label: "合作转化", count: 5, desc: "外溢进店与转化效率" },
              { icon: Database, label: "预估报价", count: 7, desc: "CPM·阅读·互动单价" },
            ].map((dim, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08, duration: 0.4 }}
                className="glass-panel rounded-xl p-5 hover:border-primary/30 transition-all group"
              >
                <div className="flex items-start justify-between mb-3">
                  <dim.icon className="w-5 h-5 text-primary/70 group-hover:text-primary transition-colors" />
                  <span className="font-data text-xs text-primary/50">
                    {dim.count} 项
                  </span>
                </div>
                <h4 className="font-semibold text-foreground mb-1 font-chinese">
                  {dim.label}
                </h4>
                <p className="text-xs text-muted-foreground font-chinese">
                  {dim.desc}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== CTA SECTION ===== */}
      <section className="relative py-32">
        <div className="container">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="relative max-w-4xl mx-auto text-center"
          >
            <div className="glass-panel rounded-2xl p-12 md:p-16 glow-red">
              <h2 className="font-display text-4xl md:text-6xl tracking-wider mb-4">
                START <span className="text-primary text-glow-red">MATCHING</span>
              </h2>
              <p className="text-muted-foreground font-chinese text-base mb-8 max-w-lg mx-auto">
                告别低效的手动筛选，让 AI 为你在星海中精准锁定目标达人
              </p>
              <Link href="/workspace">
                <span className="inline-flex items-center gap-2 px-10 py-4 text-lg font-semibold text-primary-foreground bg-primary rounded-lg hover:bg-primary/90 transition-all glow-red-strong group">
                  立即体验 {PRODUCT_NAME}
                  <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
                </span>
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="border-t border-border/30 py-8">
        <div className="container flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <img src={ASSETS.logo} alt="Σ.magic" className="h-6 w-6 rounded" />
            <span className="text-sm text-muted-foreground font-chinese">
              Σ.magic · 易美智能
            </span>
          </div>
          <p className="text-xs text-muted-foreground/50">
            &copy; {new Date().getFullYear()} Σ.magic. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
