# Causal Memory — Meeting transcript (8-21 batch)

**Source:** `8-21.rar` → 13 screenshot fragments, captured 2026-08-21 14:31–14:32
**Speakers:** `YZ` = Yujia Zheng · `MW` = Mian Wu
**Note:** the 13 fragments overlap heavily (several are re-captures of the same scroll position); duplicates have been merged and the longest version of each passage kept. ASR errors left as-is — "temporal code structure" / "color structure" = *temporal causal structure*, "quandary structure" = *ground-truth structure*, "interoperability" = *interpretability*, "Urgentic system" = *agentic system*, "a post advantage" ≈ *both advantages*, "Interesting couples" ≈ *interesting cases*.

---

**YZ:** So, for example, we got a temporal code structure, We can improve, uh, we can memorize stuff better. And, you know, easier way, and also, you know, more efficient way. So that's the first part, efficiency or effectiveness. And the second part is I actually have our trustworthiness. Because currently, there are a lot of, like, Uh, way to auditing to make sure that AI agents are safe.

**MW:** Yeah.

**YZ:** But they all have a very fundamental limitation. So we actually… Can only observe what this agent or what any machines Observe or behave, or, like, what they generate. But we actually don't know what they are thinking. So, by recovering those temporal structure latent law observed, We can actually see What really drivers the agent decision at a certain point? Maybe not as a current state point, Or at a future point, just as you mentioned. So if we if we detect something that malicious or something that is very suspicious.

**MW:** Yes.

**YZ:** Uh, we can allow the system to, uh…

**MW:** Hmm. Oh. Okay. Oh.

**YZ:** To just, yeah, to do the following actions. So I think both points are… Very important, and most importantly, They are natural result of our method. So if we can have our measure pretty good and recover reliable structure, I think we can easily show both, uh, Like, a post advantage.

**MW:** […] a suitable environment for experiments.

**YZ:** Yeah, yeah, yeah, yeah, I think that's… That might be the easiest way, like, we can't… we modify some… existing or recent work, and then we can try to show And we can recover something that being hidden or something like that. Or we can even construct those scenarios by ourselves, like…

**MW:** Hmm…

**YZ:** I don't know how the construction is. Interesting couples. Yeah, but… Yeah, anyway, like, I think… If we want to frame that paper or that project, appreciate that, uh, to fully leverage the potential of those uh, say, causal memorizations, Uh, the experiments… Should focus more on the coverage. Rather than really trying to

**MW:** Mm-hmm.

**YZ:** uh, deep dive, or do a lot of, like, experiments in Uh, one single direction. So, I may imagine that we will have three parts of experiment. And the first part is about simulation. By simulation, I mean that We can construct either the structural causal model, All the data generation process by ourselves. Right? We just have those MLP, and we have a latent variable as some random variable, and Which I'll do a simulation, and we try to see whether we can recover the correct structure, because We know the quandary structure. It is how we construct the data. So that's a need for… trying to support. Okay, our method can really recover the stature.

**YZ:** And yeah, it is something we must do. And for the second part, we try to show Uh, we can have better efficiency on the memorization or effectiveness of the memorization. Was improving the speed, or, like, minimizing the size of it, and try to get a better Memorization, uh, performance. And the third part is about… As relevant to interoperability. But the focus is not only interpretability, but as an actionable way for us to make sure Our multi-agent system, or any type of a… Urgentic system, or any type of system safe. And we exactly know Uh, what our agent have been Uh, thinking and also memory in mind, and what really drives or governs their

**YZ:** Future behavior. So… For the last two parts, we don't need to do a very comprehensive one. We just need to Focus on maybe one or two representative experiments and setup. And to show that by incorporating incorporating those color structure, We can achieve our goals. And that's it. We don't have to compare with, uh, Maybe 10% of the other… Like, baseline, like, all those existing models. So we just need to support our… Uh, story, yeah.

**YZ:** Yeah, I mean, the main part is that we try to utilize those causal structure, observe or latent. In memorization. And in order to show that there are two branches, The first is about effectiveness, and the second is about the trustworthiness. And these are the main parts we try to… uh, make our measure really… Uh, appropriate for these two. Uh, goals, and also design our experiments around them. The other part, the theory part, or like the simulation part, we can just follow or even refer to existing papers.

**MW:** Okay.
