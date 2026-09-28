"use client";

import { useState } from "react";
import type { ListingInput } from "@/types";

interface Props {
  onSubmit: (input: ListingInput) => void;
  isLoading: boolean;
}

const PRESETS: { label: string; data: ListingInput }[] = [
  {
    label: "Weak Magnesium",
    data: {
      product_title: "Magnesium 500mg 120 Capsules",
      product_description: "Magnesium supplement capsules. Take daily for health support.",
      bullet_points: [
        "500mg per capsule",
        "120 capsules per bottle",
        "Easy to swallow",
      ],
      brand_name: "HealthPlus",
      platform: "amazon",
      target_audience: "",
    },
  },
  {
    label: "Weak Vitamin C Serum",
    data: {
      product_title: "Vitamin C Serum for Face Anti Aging 30ml",
      product_description: "Face serum with vitamin C. Helps with anti aging and skin brightening.",
      bullet_points: [
        "Anti aging formula",
        "30ml bottle",
        "For all skin types",
      ],
      brand_name: "GlowSkin",
      platform: "amazon",
      target_audience: "",
    },
  },
  {
    label: "Moderate Creatine",
    data: {
      product_title: "Creatine Monohydrate Powder 5000mg - Micronized Unflavored 300g (60 Servings)",
      product_description: "Pure micronized creatine monohydrate powder for muscle strength and performance. Third-party tested for purity. Mixes easily with water or your favorite beverage. No fillers, no artificial ingredients.",
      bullet_points: [
        "PURE MICRONIZED CREATINE: 5g per serving of pharmaceutical-grade creatine monohydrate, micronized for better absorption and mixability",
        "60 SERVINGS: 300g container provides a full 2-month supply at the clinically studied 5g daily dose",
        "THIRD-PARTY TESTED: Every batch tested for purity, potency, and banned substances by an independent lab",
        "UNFLAVORED & VERSATILE: No taste, no odor — mixes into water, protein shakes, juice, or coffee without changing flavor",
        "CLEAN FORMULA: No fillers, no artificial sweeteners, no dyes. Just pure creatine monohydrate. Vegan-friendly.",
      ],
      brand_name: "NutriForce",
      platform: "amazon",
      target_audience: "Athletes and fitness enthusiasts",
    },
  },
];

export default function ListingInputForm({ onSubmit, isLoading }: Props) {
  const [form, setForm] = useState<ListingInput>({
    product_title: "",
    product_description: "",
    bullet_points: [],
    brand_name: "",
    platform: "amazon",
    target_audience: "",
  });
  const [bulletsText, setBulletsText] = useState("");

  const handlePreset = (preset: ListingInput) => {
    setForm(preset);
    setBulletsText(preset.bullet_points.join("\n"));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const bullets = bulletsText
      .split("\n")
      .map((b) => b.trim())
      .filter(Boolean);
    onSubmit({ ...form, bullet_points: bullets });
  };

  const canSubmit = form.product_title.trim().length > 0;

  return (
    <div className="glass-card p-6">
      <h2 className="text-lg font-semibold mb-4">Analyze a Product Listing</h2>

      {/* Presets */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <span className="text-xs text-[var(--text-muted)] self-center mr-1">
          Demo presets:
        </span>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => handlePreset(p.data)}
            className="px-3 py-1.5 text-xs rounded-lg border border-[var(--card-border)] hover:border-[var(--accent)] hover:bg-[var(--accent)]/5 transition-colors"
          >
            {p.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Row 1: Title + Brand */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
              Product Title *
            </label>
            <input
              type="text"
              value={form.product_title}
              onChange={(e) =>
                setForm({ ...form, product_title: e.target.value })
              }
              placeholder="e.g. Magnesium Glycinate 200mg, 60 Capsules"
              className="w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-white text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
              Brand Name
            </label>
            <input
              type="text"
              value={form.brand_name}
              onChange={(e) =>
                setForm({ ...form, brand_name: e.target.value })
              }
              placeholder="e.g. Nature Made"
              className="w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-white text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30"
            />
          </div>
        </div>

        {/* Row 2: Bullet Points */}
        <div>
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
            Bullet Points (one per line)
          </label>
          <textarea
            value={bulletsText}
            onChange={(e) => setBulletsText(e.target.value)}
            rows={4}
            placeholder={"500mg per serving\nThird-party tested\nGluten-free, vegan, non-GMO"}
            className="w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-white text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30 font-mono"
          />
        </div>

        {/* Row 3: Description */}
        <div>
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
            Product Description
          </label>
          <textarea
            value={form.product_description}
            onChange={(e) =>
              setForm({ ...form, product_description: e.target.value })
            }
            rows={3}
            placeholder="Full product description text..."
            className="w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-white text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30"
          />
        </div>

        {/* Row 4: Platform + Audience */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
              Platform
            </label>
            <select
              value={form.platform}
              onChange={(e) =>
                setForm({
                  ...form,
                  platform: e.target.value as ListingInput["platform"],
                })
              }
              className="w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-white text-sm focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="auto">Detect automatically</option>
              <option value="amazon">Amazon</option>
              <option value="walmart">Walmart</option>
              <option value="ebay">eBay</option>
              <option value="etsy">Etsy</option>
              <option value="target">Target</option>
              <option value="shopify">Shopify store</option>
              <option value="dtc">My own brand site</option>
              <option value="generic">Other</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">
              Target Audience (optional)
            </label>
            <input
              type="text"
              value={form.target_audience}
              onChange={(e) =>
                setForm({ ...form, target_audience: e.target.value })
              }
              placeholder="e.g. Women 30+, athletes"
              className="w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-white text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30"
            />
          </div>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={!canSubmit || isLoading}
          className="w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Analyzing...
            </span>
          ) : (
            "Analyze Listing"
          )}
        </button>
      </form>
    </div>
  );
}
