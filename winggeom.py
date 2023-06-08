from parapy.core import *
from parapy.geom import *
from wingsec import WingSec
from airfoil import Airfoil
from curvedraw import CurveDraw
import numpy as np
import cst


def intersection_airfoil(span_distribution, airfoil_distribution):
    frac_span = np.array(span_distribution) / span_distribution[-1]

    diff = np.ones((len(airfoil_distribution), len(airfoil_distribution)))
    inter = np.ones((len(airfoil_distribution), len(airfoil_distribution)))

    p = 0
    idx = []
    span_sec = []
    for i in range(len(frac_span)):
        diff[i] = abs(np.ones((1, len(frac_span))) * frac_span[i] - airfoil_distribution)
        if 0 not in diff[i]:
            inter[p] = diff[i]
            p = p + 1
            sorted_indices = sorted(range(len(inter[p])), key=lambda k: inter[p][k])
            idx.append(sorted_indices[:2])
            span_sec.append(frac_span[i])


    inter = inter[:p]
    return inter, idx, p, span_sec


class WingGeom(GeomBase):

    # All of the following inputs should be read from a file
    # For 1st section
    root_chord = Input(5)

    # For the rest (I have a doubt, how will we solve if the number of inputs is not coherent??)
    spans = Input([0, 8, 13, 16])           # m. wrt the root position
    tapers = Input([1, 0.6, 0.35, 0.2])     # -. wrt the root chord. Extra element for root chord
    sweeps = Input([30, 40, 50])            # deg. wrt the horizontal
    dihedrals = Input([3, 5, 10])            # deg. wrt the horizontal
    twist = Input([2, 0, -1, -3])           # def. wrt the horizontal (this includes the initial INCIDENCE!!)

    # Airfoils
    airfoil_sections = Input([0, 0.3, 0.7, 1])
    airfoil_names = Input([
        'rae5212',
        'rae5215',
        'whitcomb',
        'NACA23012'
    ])

    @Attribute
    def airfoil_guides(self):
        edges = []
        for i in range(len(self.airfoil_sections)):
            for j in range(len(self.spans)-1):
                edg = IntersectedShapes(
                    shape_in=self.airfoil_planes[i],
                    tool=self.wiresec[j].sec_plane)
                edges.append(edg.edges)

        edges = list(filter(None, edges))
        return edges

    @Attribute
    def airfoil_interp(self):
        coeff_u = np.zeros((len(self.airfoil_sections), 5))
        coeff_l = np.zeros((len(self.airfoil_sections), 5))
        for i in range(len(self.airfoil_sections)):
            coeff_u[i] = self.airfoil_unscaled[i].cst[0][0]
            coeff_l[i] = self.airfoil_unscaled[i].cst[1][0]

        inter, idx, p, s_span = intersection_airfoil(self.spans, self.airfoil_sections)

        # Linear interpolation
        airfoils = []
        for i in range(p):
            d_1 = inter[i, idx[i][0]]
            d_2 = inter[i, idx[i][1]]
            d_t = d_1 + d_2

            cst_u = d_1/d_t * coeff_u[idx[i][0], :] + d_2/d_t * coeff_u[idx[i][1], :]
            cst_l = d_1/d_t * coeff_l[idx[i][0], :] + d_2/d_t * coeff_l[idx[i][1], :]

            x_i = np.linspace(0, 1, 30)
            y_u = cst.cst(x_i, cst_u)
            y_l = cst.cst(x_i, cst_l)

            x = np.concatenate((x_i, np.flip(x_i)))
            y = np.concatenate((y_u, np.flip(y_l)))

            points = []
            for j in range(len(x)):
                points.append(Point(x[j], 0, y[j]))

            airfoils.append(points)
        return airfoils

    @Attribute
    def profile_order(self):
        inter, idx, p, s_span = intersection_airfoil(self.spans, self.airfoil_sections)
        stations = self.airfoil_sections + s_span
        sorted_indices = sorted(range(len(stations)), key=lambda k: stations[k])

        airfoils = []
        for i in range(len(self.airfoils)):
            airfoils.append(self.airfoils[i])

        for i in range(len(self.inter_airfoils)):
            airfoils.append(self.inter_airfoils[i])

        order = []
        for i in range(len(airfoils)):
            order.append(airfoils[sorted_indices[i]])

        return order

    @Part
    def wiresec(self):
        return WingSec(quantify=len(self.spans)-1,        # this is how the quantity is determined
                       span=self.spans[child.index+1]-self.spans[child.index],
                       root_chord=self.root_chord*self.tapers[child.index],
                       taper=self.tapers[child.index+1]/self.tapers[child.index],
                       map_down=['sweeps->sweep', 'dihedrals->dihedral'],
                       incidence=self.twist[child.index],
                       twist=self.twist[child.index+1],
                       position=self.position if child.index == 0 else
                       child.previous.nextorigin()
                       )

    @Part
    def airfoil_planes(self):
        return RectangularSurface(
            quantify=len(self.airfoil_sections),
            width=100*self.root_chord,
            length=100*self.root_chord,
            position=translate(rotate90(self.position, 'x'),
                               'z',
                               -self.spans[-1]*self.airfoil_sections[child.index]),
            hidden=True)

    @Part
    def airfoil_chords(self):
        return ComposedCurve(quantify=len(self.airfoil_sections),
                             built_from=self.airfoil_guides[child.index])

    @Part
    def airfoil_unscaled(self):
        return CurveDraw(quantify=len(self.airfoil_sections),
                         airfoil_name=self.airfoil_names[child.index],
                         hidden=True)

    @Part
    def airfoil_interp_unscaled(self):
        return FittedCurve(quantify=len(self.airfoil_interp),
                           points=self.airfoil_interp[child.index],
                           hidden=True)

    @Part
    def airfoils(self):
        return Airfoil(quantify=len(self.airfoil_sections),
                       airfoil_curve=self.airfoil_unscaled[child.index].foil_curve,
                       airfoil_start=self.airfoil_chords[child.index].start,
                       airfoil_direction=self.airfoil_chords[child.index].direction_vector,
                       airfoil_chord=self.airfoil_chords[child.index].length)

    @Part
    def inter_airfoils(self):
        return Airfoil(quantify=len(self.airfoil_interp),
                       airfoil_curve=self.airfoil_interp_unscaled[child.index],
                       airfoil_start=self.wiresec[child.index].sec_chords_out.start.location,
                       airfoil_direction=self.wiresec[child.index].sec_chords_out.direction_vector,
                       airfoil_chord=self.wiresec[child.index].sec_chords_out.length)

    @Part
    def right_wing(self):
        return LoftedSurface(profiles=self.profile_order)


if __name__ == '__main__':
    from parapy.gui import display
    display(WingGeom())