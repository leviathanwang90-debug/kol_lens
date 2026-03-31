import { ASSETS, PRODUCT_NAME } from "@/lib/constants";
import { Link, useLocation } from "wouter";
import { motion } from "framer-motion";

const navLinks = [
  { href: "/", label: "首页" },
  { href: "/workspace", label: "寻星工作台" },
  { href: "/library", label: "达人资产库" },
];

export function Navbar() {
  const [location] = useLocation();

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 border-b border-border/50"
      style={{
        background: "oklch(0.08 0.005 285 / 85%)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div className="container flex items-center justify-between h-16">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <img
            src={ASSETS.logo}
            alt="Σ.magic"
            className="h-9 w-9 rounded-lg object-cover transition-transform group-hover:scale-105"
          />
          <span className="font-display text-xl tracking-wider text-foreground">
            {PRODUCT_NAME}
          </span>
        </Link>

        {/* Nav Links */}
        <nav className="hidden md:flex items-center gap-1">
          {navLinks.map((link) => {
            const isActive = location === link.href;
            return (
              <Link key={link.href} href={link.href}>
                <span
                  className={`relative px-4 py-2 text-sm font-medium transition-colors rounded-md ${
                    isActive
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {link.label}
                  {isActive && (
                    <motion.span
                      layoutId="nav-indicator"
                      className="absolute bottom-0 left-2 right-2 h-0.5 bg-primary rounded-full"
                      transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
                    />
                  )}
                </span>
              </Link>
            );
          })}
        </nav>

        {/* CTA */}
        <div className="flex items-center gap-3">
          <Link href="/workspace">
            <span className="hidden sm:inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-foreground bg-primary rounded-md hover:bg-primary/90 transition-all glow-red">
              开始寻星
            </span>
          </Link>
        </div>
      </div>
    </motion.header>
  );
}
