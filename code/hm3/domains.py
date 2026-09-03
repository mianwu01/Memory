from .dgp_travel import TravelDomain


def get_domain(name: str):
    if name == "travel":
        return TravelDomain()
    if name == "shopping":
        from .dgp_shopping import ShoppingDomain
        return ShoppingDomain()
    if name == "shopping31":
        from .dgp_shopping import ShoppingDomain
        return ShoppingDomain(dense=True)
    if name == "search":
        from .dgp_search import SearchDomain
        return SearchDomain()
    if name == "formal":
        from .dgp_formal import FormalDomain
        return FormalDomain()
    raise KeyError(name)


ALL_DOMAINS = ["travel", "shopping", "search", "formal"]
