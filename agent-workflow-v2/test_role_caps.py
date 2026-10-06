"""Selected backend caps must survive ordinary task-size defaults."""
import unittest
from test_profiles import options
import profiles

class RoleCaps(unittest.TestCase):
    def test_selected_cap_survives_ordinary_recipe_and_explicit_cli_wins(self):
        profile=profiles.load('local-27b');profile['code']['reasoning_budget']=2048
        profile['sampling']={'temperature':1,'top_p':.95}
        args=options(profile='local-27b',model='27b',planner='local',executor='local')
        result=profiles.resolve(args,{'context':{'preset':'standard','max_output_tokens':16384}},profile)
        self.assertEqual(result['reasoning_budget'],2048)
        self.assertEqual(result['sampling'],{'temperature':1,'top_p':.95})
        args.reasoning_budget=8192
        self.assertEqual(profiles.resolve(args,{},profile)['reasoning_budget'],8192)

if __name__=='__main__':unittest.main()
