import itertools

from collections import namedtuple


class NotHandledError(Exception):
    pass


class ReviewDerivedVariables(object):

    """A base class to review logic used to derive values based on a list of raw values."""

    fields = []  # list of field_names to review
    models = []  # list of model classes, converts to dictionary on __init__
    visit_model = None  # visit model
    visit_model_filter = {}
    visit_model_exclude = {}
    method_prefix = 'fn_'  # test methods with this prefix
    options_prefix = 'opts_'  # generate test data from class attrs with this prefix

    def __init__(self, combinations=None, lookup_combinations=None,
                 raise_exceptions=None, run_all=None, use_unique_combinations=None, fn_name=None):
        self.data_values = {}
        self.data_exceptions = {}
        self.raise_exceptions = raise_exceptions if raise_exceptions is True else False
        self.record_class = namedtuple('Record', ' '.join(self.fields))
        self.use_unique_combinations = use_unique_combinations
        if combinations:
            self.combinations = combinations
        else:
            if lookup_combinations:
                self.combinations = self.lookup_combinations()
            else:
                self.combinations = self.generate_combinations()
        self.models = dict(zip([model._meta.object_name.lower() for model in self.models], self.models))
        self.subject_visits = self.visit_model.objects.filter(
            **self.visit_model_filter).exclude(**self.visit_model_exclude)
        self.fn_names = [fn_name] if fn_name else [fn for fn in dir(self) if fn.startswith(self.method_prefix)]
        if run_all:
            self.run_all()

    def run_all(self):
        for fn_name in self.fn_names:
            self.data_values.update({fn_name: {}})
            self.data_exceptions.update({fn_name: []})
        for record, subject_visit in self.combinations:
            for fn_name in self.fn_names:
                value = getattr(self, fn_name)(record, subject_visit)
                self.increment_counter(value, fn_name)

    def increment_counter(self, value, fn_name):
        try:
            self.data_values[fn_name][value]
        except KeyError:
            self.data_values[fn_name].update({value: 0})
        self.data_values[fn_name][value] += 1

    def generate_combinations(self):
        """Generates a list of lists that is the product of all options.

        An opts_<attr_name> class attr is expected for each field in Record."""
        opts = [getattr(self, self.options_prefix + attr) for attr in self.record_class._fields]
        for values_list in itertools.product(*opts):
            yield self.record_class(*values_list), None

    def lookup_combinations(self):
        """
        Looks up a list of lists that exist in the DB.
        """
        found = []
        for subject_visit in self.subject_visits:
            values_list = self.values_list_from(subject_visit)
            if values_list not in found:
                if self.use_unique_combinations:
                    found.append(values_list)
                yield self.record_class(*values_list), subject_visit

    def values_list_from(self, subject_visit):
        """Returns an ordered list of values from the dictionary of model instances.

        Orders the values according to the order of fields in Record.

        Return value is used to instantiate Record."""
        values_list = list(self.record_class._fields)
        for field_name in self.record_class._fields:
            values_list[values_list.index(field_name)] = self.get_field_value(field_name, subject_visit)
        return values_list

    def objects(self, subject_visit):
        """Returns dictionary of {model name: instance} for this subject_visit for each model in self.models."""
        objects = {}
        for model_name, model in self.models.items():
            try:
                obj = model.objects.get(subject_visit=subject_visit)
            except model.DoesNotExist:
                obj = model()
            objects.update({model_name: obj})
        return objects

    def get_field_value(self, field_name, subject_visit):
        """Returns the field value for `field_name` by trying each model instance."""
        value = None
        for instance in self.objects(subject_visit).values():
            try:
                value = getattr(instance, field_name)
                break
            except AttributeError:
                pass
        return value

    def records_for(self, values_list):
        for subject_visit in self.subject_visits:
            yield self.record_class(*values_list), subject_visit

    def update_exceptions(self, fn_name, record, subject_visit=None):
        if subject_visit:
            self.data_exceptions[fn_name].append([list(record), subject_visit])
        else:
            self.data_exceptions[fn_name].append(list(record))
        if self.raise_exceptions:
            raise ValueError('Unhandled record for \'{}\'. Got opts {}'.format(fn_name, list(record)))
