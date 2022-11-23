"""Tyrus module"""
# pylint: disable = too-few-public-methods, wrong-import-order, protected-access, cell-var-from-loop
# pylint: disable = too-many-instance-attributes, import-error. too-many-locals
# pylint: disable = consider-using-f-string
import numpy as np
import pandas as pd
from bokeh.io import show, output_file, output_notebook, reset_output
from bokeh.layouts import column
from bokeh.models import (
    ColumnDataSource,
    LinearColorMapper,
    ColorBar,
    Tabs,
    Panel,
    Div,
    GridBox,
)
from bokeh.plotting import figure

from trustyai.explainers import SHAPExplainer, LimeExplainer
from trustyai.utils._visualisation import bold_red_html, bold_green_html, output_html
from trustyai.utils._tyrus_info_text import LIME_TEXT, SHAP_TEXT, CF_TEXT
from trustyai.utils.data_conversions import (
    one_input_convert,
    one_output_convert,
    many_inputs_convert,
    OneInputUnionType,
    OneOutputUnionType,
    ManyInputsUnionType,
    data_conversion_docstring,
)

import java.lang


# === JAVA/PYTHON OBJECT FORMATTING ================================================================
def _formatter(value):
    """round python and java floats to 2 decimal points"""
    return "{:.2f}".format(value) if type(value) in [float, java.lang.Double] else value


def _tooltip_format(row_values):
    """format counterfactual feature tooltips"""
    return (
        "<tr> <td><b>{}:".format(row_values[0])
        + "&nbsp;</b> </td> <td>{}</td>".format(row_values[1])
        + " <td>&nbsp;&nbsp;to&nbsp;&nbsp;</td> <td>{}</td> </tr>".format(row_values[2])
    )


def _original_feature_tooltip_format(row_values):
    return (
        "<tr> <td><b>{}:&nbsp;</b> </td> <td>{}</td> <td></td> <td></td> </tr>".format(
            *row_values
        )
    )


# === TOOLTIP FORMATTERS ===========================================================================
def format_cf_tooltip(raw_tooltip, output_name, output_val, unchanged):
    """Wrap the feature toolips into a full counterfactual tooltip"""
    if unchanged:
        tooltip = "<h3>Original Input</h3>"
        tooltip += "{}: {}".format(
            output_name.split("from <b")[0].strip(), _formatter(output_val)
        )
        tooltip += "<table>"
        tooltip += raw_tooltip
        tooltip += "</table>"
    else:
        tooltip = "<h3>Counterfactual</h3>"
        tooltip += "Change {} to {} by changing:".format(
            output_name, bold_green_html(_formatter(output_val))
        )
        tooltip += "<table>"
        tooltip += raw_tooltip
        tooltip += "</table>"
    return tooltip


# === MAIN CLASS ===================================================================================
class Tyrus:
    """The TrustyAI Assistant and Dashboard.

    Tyrus is an all-in-one interface to explain and visualize a particular prediction, producing
    a Bokeh dashboard displaying a LIME, SHAP, and various counterfactual explanations`.
    """

    @data_conversion_docstring("one_input", "one_output", "many_inputs")
    def __init__(
        self,
        model,
        inputs: OneInputUnionType,
        outputs: OneOutputUnionType,
        background: ManyInputsUnionType,
        **kwargs
    ):
        r"""Initialize the :class:`Tyrus` TrustyAI assistant and dashboard.

        Parameters
        ----------
        model : :obj:`~trustyai.model.PredictionProvider`
            The TrustyAI PredictionProvider, as generated by :class:`~trustyai.model.Model`.
        inputs : {}
            The input features to the model, as a: {}
        outputs : {}
            The corresponding model outputs for the provided features, that is,
            ``outputs = model(input_features)``. These can take the form of a: {}
        background : {}
            The set of background datapoints as a: {}
        Keyword Arguments:
            * fraction_counterfactuals_to_display  : float
                (Default=0.1) The fraction of found byproduct counterfactuals to display in the
                dashboard, as a float between 0 and 1. Choose a larger number to see more,
                but this will make plot rendering more expensive.
            * notebook : bool
                (Default=False) If true, Tyrus will launch the visualizations inline in a
                Jupyter notebook. If false, the visualizations will be saved as HTML and opened
                automatically in your default browser.
        """
        self.model = model
        self.inputs = one_input_convert(inputs)
        self.outputs = one_output_convert(outputs)
        self.background = many_inputs_convert(background)
        self.fraction_counterfactuals_to_display = max(
            0, min(1, kwargs.get("fraction_counterfactuals_to_display", 0.1))
        )
        self.notebook = kwargs.get("notebook", False)

        reset_output()
        if self.notebook:
            output_notebook()
        else:
            output_file(filename="trustyai_dashboard.html", title="TrustyAI Dashboard")

        self.cfdict = None
        self.shap_saliencies = None
        self.lime_saliencies = None
        self.cf_data_source = None

    # === TRUSTYAI AUTORUNNER ======================================================================
    def _generate_saliencies(self):
        """Generate lime and shap saliencies of provided prediction."""
        shap_explainer = SHAPExplainer(
            background=self.background, track_counterfactuals=True
        )
        lime_explainer = LimeExplainer(
            samples=1000, normalise_weights=False, track_counterfactuals=False
        )
        self.shap_saliencies = shap_explainer.explain(
            inputs=self.inputs, outputs=self.outputs, model=self.model
        )
        self.lime_saliencies = lime_explainer.explain(
            inputs=self.inputs, outputs=self.outputs, model=self.model
        )

        # extract found byproduct counterfactuals
        shap_cfs = list(self.shap_saliencies._saliency_results.getAvailableCFs())
        lime_cfs = list(self.lime_saliencies._saliency_results.getAvailableCFs())

        # randomly select some to filter as per self.fraction_counterfactuals_to_display
        # this is just to speed up plot rendering
        if len(shap_cfs) + len(lime_cfs) > self.fraction_counterfactuals_to_display:
            shap_cf_idxs = np.random.choice(
                np.arange(0, len(shap_cfs)),
                int(self.fraction_counterfactuals_to_display * len(shap_cfs)),
            )
            lime_cf_idxs = np.random.choice(
                np.arange(0, len(lime_cfs)),
                int(self.fraction_counterfactuals_to_display * len(lime_cfs)),
            )
            shap_cfs = [shap_cfs[i] for i in shap_cf_idxs]
            lime_cfs = [lime_cfs[i] for i in lime_cf_idxs]

        # save found counterfactuals into cfdict
        self.cfdict = {e.getKey(): ["SHAP", e.getValue()] for e in shap_cfs}
        self.cfdict.update({e.getKey(): ["LIME", e.getValue()] for e in lime_cfs})

    def _generate_counterfactual_datasource(self):
        """Given the byproduct counterfactuals, format them into a Bokeh
        ColumnDataSource for plotting"""
        rows = []

        original_features = {
            str(f.getName()): f.getValue().getUnderlyingObject()
            for f in self.inputs.getFeatures()
        }
        formatted_features = {k: _formatter(v) for k, v in original_features.items()}
        original_output_values = {
            str(o.getName()): _formatter(o.getValue().getUnderlyingObject())
            for o in self.outputs.getOutputs()
        }

        output_names, output_column_names = [], []
        for idx, (prediction, (source_exp, preservation_mask)) in enumerate(
            self.cfdict.items()
        ):
            outputs = prediction.getOutput().getOutputs()
            if idx == 0:
                output_names = [str(o.getName()) for o in outputs]
                output_column_names = [
                    "{} from {}".format(
                        output_html(oname), bold_red_html(original_output_values[oname])
                    )
                    for oname in output_names
                ]
            row = {
                output_column_names[i]: o.getValue().asNumber()
                for i, o in enumerate(outputs)
            }
            raw_tooltip = []
            differences = 0

            original_tooltip = []
            for i, feature in enumerate(prediction.getInput().getFeatures()):
                fname = str(feature.getName())
                fval = _formatter(feature.getValue().getUnderlyingObject())
                if not preservation_mask[i]:
                    differences += 1
                    raw_tooltip.append(
                        _tooltip_format([fname, formatted_features[fname], fval])
                    )
                original_tooltip.append(
                    _original_feature_tooltip_format(
                        [fname, formatted_features[fname], fval]
                    )
                )
            raw_tooltip.append(
                _original_feature_tooltip_format(["Found by", source_exp, "", ""])
            )
            row["Tooltip Raw"] = "".join(
                original_tooltip if differences == 0 else raw_tooltip
            )
            row["Unchanged"] = differences == 0
            row["Diff"] = differences
            rows.append(row)

        data_source = pd.DataFrame(rows)
        data_source = data_source.drop_duplicates()
        data_source["Diff Jittered"] = (
            data_source["Diff"] + np.random.rand(len(data_source)) / 3
        )

        for i, output_column_name in enumerate(output_column_names):
            data_source["Tooltip " + output_names[i]] = data_source[
                ["Tooltip Raw", output_column_name, "Unchanged"]
            ].apply(
                lambda x: format_cf_tooltip(x[0], output_column_name, x[1], x[2]), 1
            )

        self.cf_data_source = data_source

    def _get_byproduct_cf_plot(self):
        """Create bokeh plot of all found byproduct counterfactuals"""
        plots = {}
        for output_field in list(self.cfdict.keys())[0].getOutput().getOutputs():
            output_name = str(output_field.getName())
            output_column_name = [
                x for x in list(self.cf_data_source) if output_name in x
            ][0]
            source = ColumnDataSource(self.cf_data_source)
            plot = figure(
                sizing_mode="stretch_both",
                title="Available Counterfactuals",
                tools=["crosshair"],
                tooltips="@{{Tooltip {}}}".format(output_name),
            )
            plot.xgrid.grid_line_color = None
            plot.xaxis.axis_label = "Counterfactual House Value"

            plot.yaxis.ticker = np.arange(0, len(self.inputs.getFeatures()))
            plot.yaxis.axis_label = "Features Changed from Original"
            exp_cmap = LinearColorMapper(
                palette="Viridis256",
                low=self.cf_data_source["Diff"].min(),
                high=self.cf_data_source["Diff"].max(),
            )
            color_bar = ColorBar(
                color_mapper=exp_cmap,
                label_standoff=12,
                title="Counterfactual Distance",
            )
            plot.add_layout(color_bar, "right")
            plot.scatter(
                output_column_name,
                "Diff Jittered",
                size=10,
                line_color={"field": "Diff", "transform": exp_cmap},
                fill_color={"field": "Diff", "transform": exp_cmap},
                source=source,
            )
            plots[output_name] = plot
        return plots

    # === DASHBOARD ================================================================================
    def _get_plots(self):
        """Grab all the plots and combine into one single Panel"""
        cf_figures = self._get_byproduct_cf_plot()
        lime_figures = self.lime_saliencies._get_bokeh_plot_dict()
        shap_figures = self.shap_saliencies._get_bokeh_plot_dict()
        output_names = list(cf_figures.keys())
        tabs = []
        for k in output_names:
            title = str(k)
            lime_tabbed = Tabs(
                tabs=[
                    Panel(child=lime_figures[k], title="LIME"),
                    Panel(
                        child=Div(text=LIME_TEXT.format(output_html(title))),
                        title="About LIME",
                    ),
                ]
            )
            shap_tabbed = Tabs(
                tabs=[
                    Panel(child=shap_figures[k], title="SHAP"),
                    Panel(
                        child=Div(text=SHAP_TEXT.format(output_html(title))),
                        title="About SHAP",
                    ),
                ]
            )

            cf_tabbed = Tabs(
                tabs=[
                    Panel(child=cf_figures[k], title="Available Counterfactuals"),
                    Panel(
                        child=Div(
                            text=CF_TEXT.format(output_html(title)),
                        ),
                        title="About Counterfactuals",
                    ),
                ]
            )

            trustyai_content = GridBox(
                children=[
                    (lime_tabbed, 0, 0, 1, 1),
                    (shap_tabbed, 1, 0, 1, 1),
                    (cf_tabbed, 0, 1, 2, 2),
                ]
            )
            joint = column(
                Div(
                    text="<h1>TrustyAI: Explaining {}</mark></h1>".format(
                        output_html(title)
                    )
                ),
                trustyai_content,
                sizing_mode="scale_width",
            )
            tabs.append(Panel(child=joint, title=title))

        full_dash = Tabs(tabs=tabs, sizing_mode="scale_width")
        return full_dash

    def run(self, display=True):
        r"""Launch Tyrus TrustyAI Assistant and launch the dashboard. Depending on the setting
        of ``tyrus.notebook`` and ``display``, this will either automatically open the
        Tyrus visualizations in a Jupyter notebook or browser window.

         Parameters
        ----------
        display = True : boolean
            Whether to automatically display the dashboard (true) or simply return it (false).
        """
        self._generate_saliencies()
        self._generate_counterfactual_datasource()
        plots = self._get_plots()

        if display:
            show(plots)
        return plots
