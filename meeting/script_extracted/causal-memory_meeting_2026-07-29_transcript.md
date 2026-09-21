# Causal Memory — Meeting transcript (7-29 batch)

**Source:** `7-29.zip` → 16 screenshot fragments, captured 2026-07-28 12:22
**Speakers:** `YZ` = Yujia Zheng · `MW` = Mian Wu
**Note:** these are ASR captions with transcription errors left as-is (e.g. "call/code/color discovery" = *causal discovery*, "Valinga/Lincum" = *VAR-LiNGAM / LiNGAM*, "Moscope" ≈ *more scalable*, "rigority" = *rigor*). Fragment #1767 is missing from the archive, so there is a gap between the slides remark and "Okay, okay, cool."

---

**MW:** Okay?

**YZ:** So there are two temporal CLs. Yes, I think here you may also… Measuring something like, uh, rather transition down. For example, x equal to… Uh, say, F… As you see. Minus one with some noise, something like that. We also have the functional dependency across different time steps. In the latent space, just the latent transition.

**YZ:** Yeah, cool. And for next time, maybe we can… Uh… first try with layer 1, because for layer 1, yes, more direct, and you can have, in addition to valid income, you can also try to search For some other ecologies, I will ask them, like in the temporal cases, And Valinga is a very, kind of, like, So maybe there is a more efficient reason why. And you can do a search and then try to apply these methods in the setting and try to see what can we discover and how to make use of them. I would suggest we can start from layer one, and after we got the first study, result for layer 1, you can try to extend it to

So two concrete stuff maybe you need to look for is that The most, say, recent, or, like, the… easy to use temporal color discovery method, and that should also be scalable, because for Agent, we are maybe dealing with hundreds or even thousands of variables. And the traditional code discovery algorithm might not be that sufficient. Because many of them were proposed, like, 10 years ago, or even 100, no, 20 years ago. Yeah, so recently, there might be some

**YZ:** So you might also want to keep a look at What are the kind of the most convenient or like the powerful benchmark? Like, for agent memory, and then try to design our module to nature face them. So in ideal cases, if there exists some, like, uh, uh, kind of like a very… Good, good toolbox, or like a… General Assembly of different methods into one GitHub report. As that would be perfect, because we can just design our module and we can immediately inject them into all different type of agent, architecture, and then try to do the evaluation. And in the most ideal cases, there should be Already some existing evaluation pipeline in those type of repositories.

**YZ:** So that would be more efficient. So these are to kind of practically cite. Uh, stuff we need to care about. And… Let me think. I think on the formulation side, I think you are totally correct, and I don't think we need to… Uh, anything further, but maybe one of the biggest things is that You can write down the functions. For example, in layer 1, There is a structured causal models. And you can refer to some relative papers. And try to see how they define the problem setup. So, for example, within the timestamp, there is a structured causal model. And that structure called the model will also have

**YZ:** some dependency across different time steps. So you should refer to some papers on those temporal call discovery. And also, as the formulation in our document here.

**YZ:** [continuing] neural network-based, say, relaxation. Or a more efficient version of this one, of this type of method. So you can do a search and try to see What method can Be the most appropriate one in our setting, so that's one thing. And the second thing is that we wanted to… Inject our module as an independent one to immediately improve the performance, the memory performance of the existing method.

**MW:** Hmm.

**YZ:** Yes, yes, sir. Yes, sir, sir. H… Oh. I saw. So here, basically, F defines the edge between the node arbitration variables x1 and X2, So in that case is a non-parametric relation between X1 and X2. And for some method, for example, by Lincum,

**YZ:** Actually, I assume. Some, like, additive noise or some other phone.

**MW:** Yes. Yeah, I see, I take a look at I have seen I have went through the

**YZ:** Yes.

**MW:** lower paper, as you can imagine, like, went through, and I think it used all… I try to construct another like B parameters. Yeah, with singular X1 and x1. And try to inference.

**YZ:** Yes, yes. Yes, exactly. So this was a kind of… different paper have different settings. And our first goal is to try to find the… photo, or more recent?

**YZ:** And I'll also send you some slides, like, Uh, regarding the call discovery in general, so you can have a global sense of that. Have I sent you before?

*[fragment #1767 missing]*

**YZ:** Okay, okay, cool. Cool. Yes, so that's great. And once we find that, College Calvary algorithm, and also we find a good Uh, say, big backbone, or, like, toolboxes, or any type of, like, platform for multi-agent memory or agent memory. Uh, systems, and then we can try to design the independent module that injects that TCD into that repository.

**YZ:** Yes, yes, exactly, and… When trying to find that temporal discovery method, one important thing you should keep in mind is that It should be scalable. So many call discovery methods are based on some

**MW:** Mm-hmm. Yeah.

**YZ:** Uh, kind of, like, a statistical method, like, uh… conditional independent test or like some rank-based information, so that not be very scalable. And some of them use neural networks. And maybe you want to take a look at those neural network based one, since that might be Moscope and also can be, Is it incorporated in an end-to-end differentiable training pipeline. So that's one thing. And for our… So I don't think we need to be… Very rigorous about the causal structure, because In some cases, there is a trade-off between the

**MW:** Hmm. Yeah.

**YZ:** readiness, like, correctness of the call structure, and the required… assumption on the data training process. So, for example, if we… Identify something, we need to put some additional constraint on the dehydrogenic process, like the linear additive noise or specific non-Gaussian assumption, something like that. But in all cases, since we are doing… essentially, we are dealing with, uh, kind of Lm, like, different agents. So we want our structure to be as practical as possible, which means that we can Try to relax those conditions. And at the same time, use a rather efficient model to do that.

**YZ:** And because we are trying to propose a problem by ourselves, this is a completely new problem. Right? It's a causal memory based on the structure. So in that cases, Any type of advancement on those type of stuff would be a huge contribution. So we don't have to really focus on a very general distribution with a rigorous theory guarantees. But as long as we can get some inspiration from those causal structure, or maybe As sudo called the stretch here, we can show the performance, and that will already be a good first step. And there will always be some extension in the future that we can work on. So…

**YZ:** I would say as a first step, please do not consider too much about the theoretical rigority, and just focus on the empirical performance. And also the convenience for your experiment and also implementation.

**YZ:** Yeah, let me… Yeah, so my just main suggestion would be that We can definitely show scalability valve with the simulation. So, by simulation means that we can

**MW:** Oh, I see, I see.

**YZ:** generate the data, right? And also, we can try to recover some structure.

**MW:** Yeah, yeah, yeah, I see it.

**YZ:** The most expensive part actually on the number of parameters of those model. Like, for example, if we are trying to deal with, uh, 100 balance of that, so even the open source model. Even the dimension might be just, like, 5,000. The number of parameters is very huge.

**YZ:** But in simulation, we can just — we can easily generate 5,000 dimension data, but with a very small Kind of cost. So we show scalability of our simulation, yeah.
