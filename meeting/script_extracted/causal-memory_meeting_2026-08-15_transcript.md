# Causal Memory — Meeting transcript (8-15 batch)

**Source:** `8-15.rar` → 10 screenshot fragments, captured 2026-08-15 00:10
**Speakers:** `YZ` = Yujia Zheng · `MW` = Mian Wu
**Note:** ASR errors left as-is — "gras" = *GRACE*, "call discovery" = *causal discovery*, "gratitude" ≈ *granularity*, "Zalt Communication paper" ≈ a prior paper of Yujia's, "memorial benchmark" = *memory benchmark*, "battery memory" ≈ *better memory*, "Acquia" = an unidentified venue (likely a conference deadline).

---

**YZ:** How many variable can gras deal with?

**MW:** I think for variables,

**YZ:** number of variables, yes.

**MW:** Yes, I think it is about… 100, originally.

**YZ:** Mm-hmm. Yeah, so for our goal, previously I indeed mentioned scalability is an issue.

**MW:** Yes.

**YZ:** If we cannot really find a way to… I really optimize the existing call discovery method. We can do some compromise relation, for example. Right, instead of treating each dimension in the LM as a single variable, we can do a grouping first. But we first try to really group them into different say, trunks or something like that, and so we can control the number of variables. So it's basically, it's… It's all about the… level of, like, gratitude we need to care about, about those type of memories. Yes.

**YZ:** Yeah, that's just a practical kind of a strategy that we can always decide later. Yeah, so because the goal of this project is really that we try to incorporate Uh, temporal structure, like, right, as we discussed before. So there are two levels.

**MW:** Yes.

**YZ:** The phrase is observed, the second is latent. So as long as we focus on that principle,

**MW:** Yes…

**YZ:** Yeah, so stability is not that big issue. I think. Uh, our main task, and maybe for you, is as a next step, is that you try to really formulate the problem precisely. Like, we now know, okay, we should try to do temporal discovery, Uh, to figure out what are the true memory. But how exactly how should we do that? And for example, as you mentioned, like, what should be the… samples, and what should be the setting, and what should be the exact scenario we need to deal with. And we need to write them down, and also, challenge us at the same time to make a formulation really solid. Before we really go deep into the experiments.

**MW:** Yeah.

**YZ:** And if we do not… If we just consider the most fundamental formulation is very clear. But when we talk about the memory, or more specifically, when you're trying to implement For example, in-memory arena or, like, memory agent benchmark or something like that. Uh, let's first figure out how we should design the experiments. And, for example, in this benchmark, do they have a different round of, like, Uh, say, conversation or something like that. And for each round, what's your piece of… definition of variable. Because the definition of variable would be quite important, like sometimes we justify variable as a single dimension in a vector.

**YZ:** Sometimes we define variable as a… aggregation of multiple variables. Sometimes we just define a single variable as a vector. And for each variable, there should be Basically, should be multiple samples. Like previously in the Zalt Communication paper, We just consider each question or each query as a sample. But in this benchmark, I haven't really read this benchmark. I'm not sure how to formulate them. So, Yeah, in general, we just need to first try to Make a good plan about how we need to implement the idea into the context of those memorial benchmark.

**MW:** I mean, does it mean that we need to first define what is the sample or of which bit?

**YZ:** Yeah, have a good plan about how to implement them, and we need to double-check on that, and once we confirm it's a good plan,

**MW:** Okay.

**YZ:** Yeah, yeah, both, because I want to accommodate that with a specific repository and also the benchmark you are trying to Implement method in. So yeah, both should be… Uh, considered. And also, in addition to this definition, you can also Uh, think about that, and also to maybe do a literature review. You already done some. about the metrics we are trying to evaluate. And also the subsidy has We try to achieve because for memory, I think there are Like, you can either purely evaluate the… to the trustworthiness of the memory, or you can try to leverage the memory to deal with some downstream tasks like inference or reasoning.

**YZ:** Your battery memory can be very helpful in various types of downstream task. And that's also something we need to consider at the beginning to have a solid plan of the experiments. We can always start from the… So simple

**YZ:** Great. And if things goes well, we can target Acquia, so you should all… Also, keep that in mind and try to make design the plan for that, yeah.
