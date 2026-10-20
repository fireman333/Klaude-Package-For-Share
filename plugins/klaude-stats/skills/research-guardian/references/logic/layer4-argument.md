# Logic Layer 4: Argument Structure Deep Guide

## 何時載入
當 Literature Guard 或 Writing Guard 啟動 Layer 4 時。

---

## 論證結構檢查的操作化步驟

### 步驟 1：論證地圖
```
將整篇文章的論證結構畫成樹狀：

主張 (Main Thesis)
  ├── 支持論點 1
  │    ├── 證據 1a
  │    └── 證據 1b
  ├── 支持論點 2
  │    └── 證據 2a
  └── 支持論點 3
       ├── 證據 3a
       └── 證據 3b

檢查：
□ 主張是否有 ≥ 2 個獨立的支持論點？
□ 每個支持論點是否有 ≥ 1 個具體證據？
□ 是否有「懸掛」的支持論點（沒有證據的主張）？
□ 證據是否直接支持其上層的論點？（不是間接的）
```

### 步驟 2：逐項謬誤掃描

#### 稻草人論證
```
偵測方法：
  1. 找到所有「反駁他人觀點」的段落
  2. 被反駁的觀點是否被準確呈現？
  3. 是否引用了原文？（不是意譯後再反駁）
  4. 是否反駁了最強版本還是最弱版本？
     → Steelmanning（反駁最強版本）> Strawmanning（反駁最弱版本）
```

#### Cherry-Picking
```
偵測方法：
  1. 支持論點的證據是否有反面證據？
  2. 文獻回顧是否包含反面結果？
  3. 作者是否討論了與其結論矛盾的研究？
  
檢查清單：
□ 是否引用了至少一篇反面結果？
□ 是否討論了 null results 或 negative findings？
□ 實驗結果是否全部報告（包括失敗的）？
```

#### 滑坡謬誤
```
偵測信號：
  "if we allow X, then Y will happen, and eventually Z"
  
偵測方法：
  1. 從 X 到 Y 的步驟是否有獨立證據？
  2. 從 Y 到 Z 的步驟是否有獨立證據？
  3. 每一步的機率是否被評估？
  4. 是否假設了不可避免的連鎖反應？
```

#### 合成/分割謬誤
```
合成：部分好 → 整體好
  偵測信號："each component works well, so the system works well"
  修正：討論組件間的交互作用和整合測試結果

分割：整體好 → 部分好
  偵測信號："overall accuracy is 90%, so all subtasks are handled well"
  修正：報告各子任務/子群體的個別表現
```

#### 移動門柱
```
偵測方法：
  1. Introduction 中設定的目標是什麼？
  2. Results 中報告的成功標準是否與之一致？
  3. Discussion 中是否重新定義了成功？
  
偵測信號：
  "While we did not achieve [original goal], our approach shows
   promise in [different metric]"
  → 如果誠實承認 = OK
  → 如果偷偷換了成功標準 = 🔴
```

#### 訴諸權威
```
可接受：引用該領域的專家研究作為證據
不可接受：引用非領域專家的觀點作為論據
不可接受：引用機構名稱代替具體證據
  ❌ "Google says X, so X is true"
  ✅ "Research by [specific authors at Google] found X [citation]"
```

### 步驟 3：論證完整性
```
□ 是否回應了所有合理的反對意見？
□ 是否討論了替代解釋？
□ 是否承認了局限性？（至少 3 項具體的）
□ 結論是否與前文的論證一致？（不突然引入新主張）
```
