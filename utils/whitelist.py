from typing import Optional, List, Dict
from enum import Enum
import yaml
import re

class Permit(Enum):
    ALLOW = True
    DENY = False

    def __bool__(self):
        return self.value

class User:
    def __init__(self, name:str, password:str):
        self.name = name
        self.password = password
        self.groups = []

    def get_groups(self) -> List:
        return self.groups

    def __repr__(self):
        return f"<User name=\"{self.name}\">"

class Group:
    def __init__(self, name):
        self.name = name
        self.members = []

    def get_members(self) -> List[User]:
        return self.members

    def __repr__(self):
        return f"<Group name=\"{self.name}\">"

class Rule:
    def __init__(self, permit:Permit, principal, pattern:str):
        self.permit = permit
        self.principal = principal
        self.pattern = re.compile(pattern)
    
    def matches(self, path):
        return self.pattern.fullmatch(path) != None

class ACL:
    def __init__(self):
        self.users:Dict[str, User] = {}
        self.groups:Dict[str, Group] = {}
        self.rules:List[Rule] = []

    def create_group(self, name):
        group = Group(name)
        self.groups[name] = group
        return group
    
    def create_user(self, name, password):
        user = User(name, password)
        self.users[name] = user
        return user
    
    def get_group(self, name) -> Optional[Group]:
        return self.groups.get(name)

    def get_user(self, name) -> Optional[User]:
        return self.users.get(name)
    
    def add_user(self, user:User, group:Group):
        user.groups.append(group)
        group.members.append(user)

    def remove_user(self, user:User, group:Group):
        user.groups.remove(group)
        group.members.remove(user)

    def add_rule(self, rule:Rule):
        self.rules.append(rule)

    def match_any(self, path:str):
        for rule in self.rules:
            if rule.matches(path):
                return True

        return False

    def can_access(self, principal, path:str) -> bool:
        if not path.startswith("/"):
            path = "/"+path

        rules = []
        
        for rule in self.rules:
            if type(principal) == User:
                if rule.principal in principal.get_groups():
                    rules.append(rule)
                    
            if rule.principal == principal:
                rules.append(rule)
                
        for rule in rules:
            if rule.matches(path):
                return bool(rule.permit)

        return False

    @classmethod
    def from_yaml(cls, stream):
        data = yaml.safe_load(stream)
        users = data.get("users", {})
        groups = data.get("groups", {})
        rules = data.get("rules", {})

        acl = cls()

        everyone = acl.create_group("everyone")
        logged = acl.create_group("logged")

        for user, password in users.items():
            user = acl.create_user(user, password)
            acl.add_user(user, everyone)
            acl.add_user(user, logged)

        for name, members in groups.items():
            group = acl.create_group(name)
            for member in members:
                user = acl.get_user(member)
                if user is not None:
                    acl.add_user(user, group)

        for rule in rules:
            permit = Permit[rule.get("permit", "deny").upper()]
            principal = rule.get("principal", "")
            pattern = rule.get("pattern")

            if principal.startswith("user:"):
                principal = acl.get_user(principal[5:])
            elif principal.startswith("group:"):
                principal = acl.get_group(principal[6:])
            else:
                continue

            rule = Rule(
                permit,
                principal,
                pattern
            )

            acl.add_rule(rule)
            
        return acl


if __name__ == "__main__":
    def test_check(acl:ACL, path:str):
        print(f"{path} :")

        for user in acl.users.values():
            permit = acl.can_access(user, path)
            print(f"  user:{user.name} {'✅' if permit else '❌'}")

        for group in acl.groups.values():
            permit = acl.can_access(group, path)
            print(f"  group:{group.name} {'✅' if permit else '❌'}")

        print("")

    acl = ACL()

    # Users
    bob = acl.create_user("bob", "")
    alice = acl.create_user("alice", "")

    # Groups
    everyone = acl.create_group("everyone")
    acl.add_user(bob, everyone)
    acl.add_user(alice, everyone)

    # Rules
    alice_zines_rule = acl.add_rule(Rule(
        Permit.ALLOW,
        alice,
        r"\/zines(\/[a-zA-Z.,;!'_ ]+\.pdf)?"
    ))

    public_dir_rule = acl.add_rule(Rule(
        Permit.ALLOW,
        everyone,
        r"\/public(\/[a-zA-Z,;!\/'_ ]+\.[a-zA-Z\/,;!'_ ]+)?"
    ))

    # Tests
    test_check(acl, "/public/rule.odt")
    test_check(acl, "/zines/test.pdf")
    test_check(acl, "/zines")
    test_check(acl, "/public/../public/test.escaping")
