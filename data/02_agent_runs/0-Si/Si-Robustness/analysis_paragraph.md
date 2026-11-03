# Si refinement robustness across three dimensions

Three dimensions are probed on the same material — Si (NIST SRM 640g, TOF neutron,
MPI at CSNS, bank 5 centred at 2θ = 95°, flight path 30.0 m):

| dimension | projects | varies |
|---|---|---|
| sampling temperature | 3 | temperature parameter 0 / 0.5 / 1 |
| prompt phrasing | 3 | wording of the instruction given to the agent |
| detector level | 3 | module-level / bank-level / group-level reconstructed data |

Reference cell: NIST SRM 640g certified **a = 5.431109(80) Å** (k = 2). Deviations are
quoted in ppm against this value.

**Two caveats that bound the interpretation.** (i) Module, bank and group data are
reconstructions of the *same* measurement and share counts, so the detector dimension
is a set of correlated, not independent, realisations. (ii) The instrument parameter
file used for all routes is bank-5 calibrated and was deliberately applied also to the
bank-3 module data; the 1134 ppm cell spread of that dimension is therefore an
upper bound on detector-level sensitivity rather than a calibrated result.

---

## Analysis (English)

> Three axes of variation were probed on a single certified standard to establish how
> sensitive the refinement is to factors that carry no crystallographic information.
> The clearest result is a decoupling of fit quality from structural accuracy. Across
> the three sampling-temperature settings the weighted profile R factor varies by
> 66 % in relative terms (4.520 %, 5.275 % and 7.509 %), yet the refined cubic lattice
> parameter is essentially invariant, spanning only 5.425218–5.425425 Å — a range of
> 38 ppm, or 0.0002 Å. Because a temperature parameter cannot alter the lattice
> constant of a silicon crystal, the entire spread in Rwp must originate in the
> refinement path and in the number of parameters that path chose to free (8, 13 and
> 14 across the three runs, with the largest parameter count producing the worst fit).
> Reporting Rwp alone would therefore have conveyed the opposite of what the data
> show.
>
> Prompt phrasing is the most benign axis: Rwp spans 4.623–5.165 % (6.2 % relative
> scatter) and the cell spans 135 ppm, with the fitted isotropic displacement
> parameter of silicon essentially identical between phrasings (0.00713–0.00720 Å²).
> The crystallographic answer is reproduced regardless of how the task is worded, and
> the residual variation is again explained by differing refinement choices — one
> phrasing refined the σ family of TOF profile terms while the other two refined the
> β family.
>
> Detector level dominates. The refined cell edge ranges over 1134 ppm, from
> 5.418549 Å (bank level) to 5.424709 Å (group level), with the module-level result at
> 5.419556 Å; the spread is nearly thirty times that of the prompt dimension and is
> comparable to the systematic offset from the certified value itself. Notably, the
> three levels rank *oppositely* for the two figures of merit: module-level data gives
> the lowest Rwp (4.424 %) but the second-worst cell (−2127 ppm), whereas group-level
> data gives a substantially higher Rwp (5.165 %) and the best cell (−1178 ppm). Had
> the comparison been made on Rwp alone, the module-level refinement would have been
> judged the most reliable of the three; by the metrologically meaningful criterion it
> is among the least reliable. This is the central practical finding of the study: for
> these data the R factor is not a surrogate for lattice-parameter accuracy.
>
> The diagnostics locate the mechanism. Every one of the eleven refinements carries a
> Scale–Absorption correlation of 96.6–98.7 %, so that pair is unidentifiable
> throughout and should be constrained rather than refined freely. More seriously, in
> two of the eleven refinements the cell parameter and the TOF `alpha` profile term are
> 97.5 % correlated — above the 95 % threshold at which a least-squares pair ceases to
> be separable. Both occurrences are in the group-level route (the prompt-A and
> expert-informed refinements), which is the route that also returns the most accurate
> cell; the correlation is therefore not a marker of a bad result but an indication
> that the cell is being supported by the profile term rather than determined
> independently of it.
>
> It is important to be precise about what the detector-level spread is *not*. In all
> eleven refinements `difC`, `difA` and `Zero` were held at their file values
> (10265.471 µs Å⁻¹, −2.774 µs Å⁻² and 38.367 µs respectively), so the cell–`difC`
> degeneracy — which reaches 99.5 % when both are free — was never given the
> opportunity to act, and the 1134 ppm spread is not a re-calibration. What differs
> between the three detector routes is instead (i) which detector elements were merged
> into the pattern and (ii) which profile terms were freed: the module-level fit
> refined the Lorentzian `X` and `Y` terms while the bank- and group-level fits refined
> the Gaussian `sig-0…sig-q` family instead. The most defensible reading is therefore
> that the spread arises from the data-reduction choice combined with a 97.5 %
> cell–profile entanglement, and, for the module level specifically, from applying a
> bank-5 calibration to bank-3 data. The practical consequence is unchanged and in fact
> strengthened: the lattice parameter obtained from this material is conditional on the
> detector-level and profile-settings choices, at the 10³ ppm level, and a single-route
> cell should not be presented as the material's lattice parameter without that
> qualification.
>
> Taken together, the experiment supports a qualified conclusion. The refinement is
> robust to prompt phrasing and, for the lattice parameter, to the sampling
> temperature; it is *not* robust to the detector level from which the pattern is
> reconstructed, where the cell moves by more than a thousand ppm while Rwp moves in
> the opposite direction. Rwp should consequently be reported alongside — and
> subordinate to — the deviation of the refined cell from its certified value, and
> lattice parameters obtained under different detector-level or profile-term choices
> should be reported as such rather than pooled into a single value. It should also be
> noted that the instrument constants were held fixed throughout this study, so the
> spread reported here is a *lower* bound on what would be obtained if the calibration
> were allowed to float together with the cell.

---

## 中文翻译

> 我们在同一种认证标准物质上考察了三个变量轴，以确定精修对不含晶体学信息因素的敏感程度。
> 最清晰的结果是拟合质量与结构准确度之间的解耦。在三个采样温度设置下，加权剖面 R 因子
> 相对变化达 66 %（4.520 %、5.275 %、7.509 %），但精修得到的立方晶胞参数几乎不变，仅为
> 5.425218–5.425425 Å——跨度 38 ppm，即 0.0002 Å。由于温度参数不可能改变硅晶体的晶格常数，
> Rwp 的全部离散必然源自精修路径以及该路径所释放的参数个数（三次运行分别为 8、13、14 个，
> 参数最多者拟合最差）。因此，仅报告 Rwp 会传达与数据相反的信息。
>
> 提示词措辞是最温和的一轴：Rwp 为 4.623–5.165 %（相对离散 6.2 %），晶胞跨度 135 ppm，
> 且硅的各向同性位移参数在不同措辞间基本一致（0.00713–0.00720 Å²）。无论任务如何表述，
> 晶体学答案都能复现，残余差异同样可由精修选择不同来解释——其中一种措辞精修了 TOF 轮廓的
> σ 项族，另外两种精修了 β 项族。
>
> 探测器层级的影响居于主导。精修晶胞边长跨越 1134 ppm，从 5.418549 Å（bank 级）到
> 5.424709 Å（group 级），module 级为 5.419556 Å；该离散约为提示词维度的三十倍，与相对
> 认证值的系统偏差本身相当。值得注意的是，三个层级在两个评价指标上的排序**完全相反**：
> module 级数据给出最低的 Rwp（4.424 %）但晶胞次差（−2127 ppm），而 group 级数据给出明显
> 更高的 Rwp（5.165 %）却给出最好的晶胞（−1178 ppm）。若仅凭 Rwp 比较，module 级精修会被
> 判为三者中最可靠；而按计量学上有意义的判据，它属于最不可靠之列。这是本研究的核心实践结论：
> 对这批数据而言，R 因子不能作为晶胞参数准确度的替代指标。
>
> 诊断结果揭示了机理。十一次精修**无一例外**都带有 96.6–98.7 % 的 Scale–Absorption 相关，
> 说明该参数对始终不可辨识，应当加以约束而非自由精修。更严重的是，十一次中有两次，晶胞参数
> 与 TOF 的 `alpha` 轮廓项相关性达 97.5 %——已超过最小二乘参数对不可分离的 95 % 阈值。这两次
> 都出现在 group 级路线（prompt A 与引入专家知识的那次），而该路线同时给出了最准确的晶胞；
> 可见这一相关并非"结果不佳"的标志，而是表明晶胞是由轮廓项在支撑，而非独立于它被确定。
>
> 有一点必须精确说明：探测器层级的离散**并不是**什么。在全部十一次精修中，`difC`、`difA` 与
> `Zero` 均固定于其文件值（分别为 10265.471 µs Å⁻¹、−2.774 µs Å⁻²、38.367 µs），因此晶胞–`difC`
> 简并（两者同时自由时可达 99.5 %）从未有机会起作用，1134 ppm 的离散并非重新标定。三条探测器
> 路线真正的差异在于：（i）哪些探测器单元被合并进图谱；（ii）释放了哪些轮廓项——module 级精修了
> 洛伦兹 `X`、`Y` 项，而 bank 级与 group 级改为精修高斯 `sig-0…sig-q` 项族。因此最稳妥的解读是：
> 该离散源自数据重建方式的选择，叠加 97.5 % 的晶胞–轮廓纠缠；就 module 级而言，还额外叠加了把
> bank 5 标定用于 bank 3 数据的问题。其实践后果不变、甚至更强：由该材料得到的晶格参数依赖于探测器
> 层级与轮廓设置的选择，量级达 10³ ppm，因此不应在未加说明的情况下把单一路线的晶胞当作该材料的
> 晶格参数来报告。
>
> 综合来看，本实验支持一个有保留的结论：精修对提示词措辞稳健，对晶格参数而言对采样温度也
> 稳健；但它对数据重建所依据的探测器层级**并不**稳健——在那里晶胞移动超过一千 ppm，而 Rwp
> 却朝相反方向移动。因此，Rwp 应当与精修晶胞相对认证值的偏差一并报告，并处于从属地位；在不同
> 探测器层级或轮廓项设置下得到的晶格参数，应如实分别报告，而不应合并为单一数值。还需说明的是，
> 本研究全程固定了仪器常数，故此处报告的离散是"若允许标定与晶胞一同浮动"时所会得到的离散的
> **下界**。

---

## Figure captions

**Figure 1 | Robustness of the Si refinement along three axes.**
Each symbol is one refinement; horizontal bars give the dimension mean and dotted
vertical lines the dimension range. Left: weighted profile R factor. Centre: goodness
of fit (logarithmic). Right: deviation of the refined cubic lattice parameter from the
NIST SRM 640g certified value, with the ±1 ppm band shaded. Rwp varies strongly across
temperature and detector dimensions, whereas the lattice parameter is nearly invariant
with temperature and moves by >1000 ppm with detector level.

**图 1 | 硅精修在三个变量轴上的鲁棒性。**
每个符号代表一次精修；横线为各维度均值，竖虚线为维度极差。左：加权剖面 R 因子。
中：拟合优度（对数坐标）。右：精修立方晶胞参数相对 NIST SRM 640g 认证值的偏差，
灰色带为 ±1 ppm。Rwp 在温度与探测器维度变化显著，而晶格参数随温度几乎不变、
随探测器层级移动超过 1000 ppm。

**Figure 2 | Per-refinement comparison.**
Left: Rwp. Right: deviation of the refined cell from the certified value. Colours denote
the dimension. Note that the module-level refinement achieves the lowest Rwp but one of
the largest cell deviations, i.e. the two criteria rank the routes differently.

**图 2 | 逐次精修对比。**
左：Rwp。右：精修晶胞相对认证值的偏差。颜色表示所属维度。注意 module 级精修取得了
最低的 Rwp，却也是晶胞偏差最大的之一，即两个判据对路线的排序并不一致。

---

## Data summary

| Dimension | Route | Rwp (%) | GOF | N var | a (Å) | Δa (ppm) | min U_iso (Å²) |
|---|---|---|---|---|---|---|---|
| Temperature | T = 0 | 4.520 | 64.34 | 14 | 5.425218 | −1085 | 0.00666 |
| Temperature | T = 0.5 | 5.275 | 74.94 | 8 | 5.425397 | −1052 | 0.00585 |
| Temperature | T = 1 | 7.509 | 106.87 | 13 | 5.425425 | −1047 | 0.00213 |
| Prompt | prompt A | 5.165 | 73.47 | 12 | 5.424709 | −1178 | 0.00713 |
| Prompt | prompt B | 4.623 | 65.79 | 13 | 5.425442 | −1043 | 0.00720 |
| Prompt | prompt C | 4.674 | 66.44 | 10 | 5.425439 | −1044 | 0.00720 |
| Detector | module level | 4.424 | 20.12 | 22 | 5.419556 | −2127 | 0.00537 |
| Detector | bank level | 7.182 | 46.87 | 12 | 5.418549 | −2313 | 0.00753 |
| Detector | group level | 5.165 | 73.47 | 12 | 5.424709 | −1178 | 0.00713 |

**Spread within each dimension**

| Dimension | Rwp range (%) | Rwp rel. sd (%) | Δa range (ppm) | Δa rel. sd (%) |
|---|---|---|---|---|
| Temperature | 2.990 | 26.95 | 38 | 1.95 |
| Prompt | 0.542 | 6.21 | 135 | 7.14 |
| Detector | 2.758 | 25.53 | 1134 | 32.48 |
