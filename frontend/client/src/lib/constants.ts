// Brand & Product
export const BRAND_NAME = "Σ.magic";
export const PRODUCT_NAME = "Σ.Match";
export const PRODUCT_TAGLINE = "智能寻星工作站";
export const PRODUCT_SUBTITLE = "AI驱动的KOL智能匹配与资产管理平台";

// CDN Assets
export const ASSETS = {
  logo: "https://d2xsxph8kpxj0f.cloudfront.net/310519663489477361/NvK7QhZsHdWyUmbLncQLcR/logo_f7c1faf3.jpg",
  heroBg: "https://d2xsxph8kpxj0f.cloudfront.net/310519663489477361/NvK7QhZsHdWyUmbLncQLcR/hero-bg-R2ffbnpQqDeFWiFK3LJCTE.webp",
  workspaceBg: "https://d2xsxph8kpxj0f.cloudfront.net/310519663489477361/NvK7QhZsHdWyUmbLncQLcR/workspace-bg-Z5q6MSXK83LkQ5HUrZcw6V.webp",
  featureAi: "https://d2xsxph8kpxj0f.cloudfront.net/310519663489477361/NvK7QhZsHdWyUmbLncQLcR/feature-ai-6hQw2cTr5tyh4UYhtsgUyv.webp",
  featureData: "https://d2xsxph8kpxj0f.cloudfront.net/310519663489477361/NvK7QhZsHdWyUmbLncQLcR/feature-data-nNNx5X3b2QAFXKEBnN3pQj.webp",
  featureLibrary: "https://d2xsxph8kpxj0f.cloudfront.net/310519663489477361/NvK7QhZsHdWyUmbLncQLcR/feature-library-Frgy55q86JMDgYLEfCz6kB.webp",
} as const;

// Role definitions
export const ROLES = [
  { id: 1, label: "采购", weight: "基础权重" },
  { id: 2, label: "策划/前端", weight: "中等权重" },
  { id: 3, label: "客户", weight: "最高权重" },
] as const;

// Data grid column groups
export const COLUMN_GROUPS = {
  basic: { label: "基础视图", columns: ["博主信息", "近期笔记", "粉丝数", "粉丝量变化幅度", "活跃粉丝占比", "互动粉丝占比"] },
  daily: { label: "日常大盘", columns: ["曝光中位数(日常)", "阅读中位数(日常)", "互动中位数(日常)", "千赞笔记比例", "百赞笔记比例"] },
  image: { label: "图文表现", columns: ["图文曝光中位数", "图文阅读中位数", "图文互动中位数", "图文千赞比例", "图文百赞比例"] },
  video: { label: "视频表现", columns: ["视频曝光中位数", "视频阅读中位数", "视频互动中位数", "视频千赞比例", "视频百赞比例", "视频完播率"] },
  collab: { label: "合作转化", columns: ["曝光中位数(合作)", "阅读中位数(合作)", "互动中位数(合作)", "外溢进店中位数", "外溢进店单价"] },
  pricing: { label: "预估报价", columns: ["图文CPM", "图文阅读单价", "图文互动单价", "视频CPM", "视频阅读单价", "视频互动单价", "全部报价"] },
} as const;
